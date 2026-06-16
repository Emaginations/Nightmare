"""
喊你睡觉：一个简单的催睡插件

2026-5-22 建立项目,尝试将WebUI配置中文本地化
2026-5-23 调整催睡时间设置的时间格式，添加睡眠时长sleep_hours
2026-5-24 增补readme.md，进行详细功能说明(设计),添加无差别催睡功能，默认关闭，新增白名单
2026-5-25 实现白名单的webui配置UI,添加用于测试的webui聊天用户名
2026-5-26 实现主体功能。用config = await self.ctx.config.get_plugin("com.example.my-plugin")尝试获取睡眠晚安插件的作息表
2026-5-28 正在测试
2026-5-31 try16: 添加状态文件持久化，避免重启丢失催睡记录（互动/催睡时间）
2026-6-03 try17: 优化LLM调用（检查模型可用性，自动回退默认模型），/night /nightmare 命令返回空
2026-6-04 try18: 日志添加LLM模型名；非WebUI命令静默忽略（不发送消息）
2026-6-05 try19: 催睡概率步进值改为0.01
2026-6-08 try20: 重构催睡逻辑；封装为 LLMProvider，插件自身通过 Provider 生成内容，默认 DeepSeek API，新增 temperature 配置
2026-6-10 try21: 新增群聊白名单（免催）；HOOK 改回 BLOCKING 强制发送，日志添加目标群号
2026-6-11 try22: 在 _do_remind 添加 send.text 诊断日志，记录发送结果
2026-6-12 try23: 修复 stream_id 为空问题（优先取 session_id，群聊时通过 chat API 反查）
2026-6-12 try24: 修复时间窗口逻辑（支持跨天）；无差别催睡改为催促发话人而非目标用户；LLM提示词隐藏添加催睡时间；UI文案优化
2026-6-13 try25: 名字出现概率（私聊0.8/无差别0.3，间隔越短越低最小0.01）；新增沉默模式；LLM附带改为催睡时间+当前时间；
           插件自行随机决定昵称前后置，不再传给LLM；所有命令统一受webui_only_commands限制；
           使用WebUI中配置的LLM提示词；修改默认提示词；prompt中隐藏添加去昵称、去引号要求
Q：应该在什么时候获取聊天流？A：收到消息的时候（ON_MESSAGE?）
Q：应该在什么地方获取聊天流？A：尝试在@HookHandler或@EventHandler用self.ctx.chat或尝试新的获取方法：
按时间范围查询指定聊天流
messages = await self.ctx.message.get_by_time_in_chat(
    chat_id=stream_id,
    start_time=start_time,
    end_time=end_time,
)
Q：如何获得ID、昵称：A：参考
通过 person API 获取用户信息
person_id = await self.ctx.person.get_id("qq", target_user_id)
person_name = await self.ctx.person.get_value(person_id, "person_name")
nickname = await self.ctx.person.get_value(person_id, "nickname")
Q：[喊你睡觉]LLM调用异常: [E_CAPABILITY_DENIED] 插件 1m.nightmare 未获授权能力: message.get_recent??
A: _manifest.json 中需要添加权限
"""

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command, EventHandler, HookHandler, LLMProvider, LLMProviderBase
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType, HookMode, HookOrder
from typing import Dict, Optional, ClassVar, List, Any
import asyncio
import random
import time
import datetime
import json
import os
import aiohttp

# ============================================================================
# 多语言化
# ============================================================================
def _schema_i18n(
    *,
    label_en: str,
    label_ja: str,
    hint_en: Optional[str] = None,
    hint_ja: Optional[str] = None,
    placeholder_en: Optional[str] = None,
    placeholder_ja: Optional[str] = None,
) -> Dict[str, Dict[str, str]]:
    i18n: Dict[str, Dict[str, str]] = {
        "en_US": {"label": label_en},
        "ja_JP": {"label": label_ja},
    }
    if hint_en is not None:
        i18n["en_US"]["hint"] = hint_en
    if hint_ja is not None:
        i18n["ja_JP"]["hint"] = hint_ja
    if placeholder_en is not None:
        i18n["en_US"]["placeholder"] = placeholder_en
    if placeholder_ja is not None:
        i18n["ja_JP"]["placeholder"] = placeholder_ja
    return i18n

# ============================================================================
# WebUI插件控件生成
# ============================================================================
class NightmarePluginSection(PluginConfigBase):
    """插件基本配置。"""
    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0
    enabled: bool = Field(default=False, description="是否启用喊你睡觉插件", json_schema_extra={"label": "开关", "i18n": _schema_i18n(label_en="Enable", label_ja="アダプターを有効化"), "order": 0})
    config_version: str = Field(default="2.0.0", description="配置版本", json_schema_extra={"label": "配置版本", "i18n": _schema_i18n(label_en="Config version", label_ja="設定バージョン", hint_en="Configuration version number.", hint_ja="設定のバージョン番号。"), "order": 1})


class SchedulerConfig(PluginConfigBase):
    """催睡时间设置。"""
    __ui_label__: ClassVar[str] = "催睡时间"
    __ui_order__: ClassVar[int] = 1

    target_user: str = Field(default="", description="催促对象（QQ号、微信号或其他平台用户ID）", json_schema_extra={"label": "催促对象", "hint": "在这里设定催促对象", "placeholder": "请输入用户ID", "i18n": _schema_i18n(label_en="Target user", label_ja="催促対象", hint_en="Set the target user to remind.", hint_ja="催促する対象を設定します。", placeholder_en="Enter user ID", placeholder_ja="ユーザーIDを入力"), "order": 0})
    test_user: str = Field(default="WebUI用户", description="用于从webUI测试", json_schema_extra={"label": "webui聊天用户名", "hint": "用户名位于webui聊天室左下角", "i18n": _schema_i18n(label_en="WebUI chat username", label_ja="WebUIチャットユーザー名", hint_en="For testing only.", hint_ja="テスト専用。"), "placeholder": "WebUI用户", "order": 0})
    webui_only_commands: bool = Field(default=True, description="是否只有WebUI聊天可以触发命令", json_schema_extra={"label": "命令仅限WebUI", "hint": "开启后所有命令仅在WebUI聊天中可用", "i18n": _schema_i18n(label_en="Commands only in WebUI", label_ja="コマンドはWebUIのみ"), "order": 1})
    start_time: str = Field(default="22:00", pattern=r"^([01]\d|2[0-3]):([0-5]\d)$", description="催睡开始时间（格式 HH:MM，例如 22:00）", json_schema_extra={"label": "开始时间", "placeholder": "22:00", "i18n": _schema_i18n(label_en="Start time", label_ja="開始時間"), "order": 2})
    sleep_hours: float = Field(default=8, ge=4, le=12, description="睡眠时长（小时）", json_schema_extra={"label": "睡眠时长（小时）", "hint": "低于这个时间间隔发言会被继续催促", "x-widget": "slider", "min": 4, "max": 12, "step": 0.5, "i18n": _schema_i18n(label_en="Sleep hours", label_ja="睡眠時間"), "order": 3})
    silent_mode: bool = Field(default=False, description="沉默模式：开启后拦截消息但不发送任何内容", json_schema_extra={"label": "沉默模式", "hint": "沉默...是最好的陪伴", "i18n": _schema_i18n(label_en="Silent Mode", label_ja="サイレントモード", hint_en="Silence... is the best company.", hint_ja="沈黙...は最高の仲間です。"), "order": 4})


class ReminderConfig(PluginConfigBase):
    """提醒频率与重复设置。"""
    __ui_label__: ClassVar[str] = "提醒设置"
    __ui_order__: ClassVar[int] = 2

    interval_seconds: int = Field(default=30, ge=5, le=120, description="两次催睡之间的最小间隔（秒）", json_schema_extra={"label": "提醒间隔（秒）", "hint": "默认30秒，防止短时间内重复催睡", "i18n": _schema_i18n(label_en="Interval (seconds)", label_ja="間隔（秒）"), "order": 0})
    remind_probability: float = Field(default=1.0, ge=0.0, le=1.0, description="催睡概率", json_schema_extra={"label": "催睡概率", "hint": "满足条件后实际发送的概率", "x-widget": "slider", "min": 0, "max": 1, "step": 0.01, "i18n": _schema_i18n(label_en="Remind probability", label_ja="リマインド確率"), "order": 1})


class LLMConfig(PluginConfigBase):
    """LLM提示词设置（独立提供商）"""
    __ui_label__: ClassVar[str] = "LLM提示词设置"
    __ui_order__: ClassVar[int] = 3

    enable_llm: bool = Field(default=True, description="是否启用LLM", json_schema_extra={"label": "是否启用LLM", "i18n": _schema_i18n(label_en="Enable LLM", label_ja="LLMを有効にする"), "order": 0})
    # 修改默认提示词
    llm_text: str = Field(default="请根据上下文生成一句不重复的简短催睡语句，不要包含用户昵称。", description="LLM提示词", json_schema_extra={"label": "LLM提示词", "hint": "自定义LLM生成指令，不要包含用户昵称，已自动附加", "i18n": _schema_i18n(label_en="LLM prompt", label_ja="LLMプロンプト"), "order": 1})
    api_base: str = Field(default="https://api.deepseek.com", description="API 地址", json_schema_extra={"label": "API 地址", "placeholder": "https://api.deepseek.com", "i18n": _schema_i18n(label_en="API Base URL", label_ja="APIベースURL"), "order": 2})
    api_key: str = Field(default="", description="API 密钥", json_schema_extra={"label": "API 密钥", "placeholder": "sk-...", "i18n": _schema_i18n(label_en="API Key", label_ja="APIキー"), "order": 3})
    model_name: str = Field(default="deepseek-chat", description="模型名称", json_schema_extra={"label": "模型名称", "placeholder": "deepseek-chat", "i18n": _schema_i18n(label_en="Model Name", label_ja="モデル名"), "order": 4})
    temperature: float = Field(default=0.8, ge=0.0, le=2.0, description="生成温度", json_schema_extra={"label": "温度 (Temperature)", "x-widget": "slider", "min": 0.0, "max": 2.0, "step": 0.1, "i18n": _schema_i18n(label_en="Temperature", label_ja="温度"), "order": 5})


class DefualtGoodNightConfig(PluginConfigBase):
    """默认晚安设置。"""
    __ui_label__: ClassVar[str] = "默认晚安设置"
    __ui_order__: ClassVar[int] = 4
    default_good_night: str = Field(default="睡吧", description="喊你睡觉", json_schema_extra={"label": "默认晚安", "hint": "睡吧", "i18n": _schema_i18n(label_en="Default good night", label_ja="デフォルトの夜寝"), "order": 0})


class JamReminderConfig(PluginConfigBase):
    """无差别催睡配置"""
    __ui_label__: ClassVar[str] = "无差别催睡"
    __ui_order__: ClassVar[int] = 5

    enable_jam_reminder: bool = Field(default=False, description="是否启用无差别催睡", json_schema_extra={"label": "启用无差别催睡", "hint": "开启后，任何人发消息都会被催睡（白名单除外）", "i18n": _schema_i18n(label_en="Enable Jam Reminder", label_ja="無差別催促を有効にする"), "order": 0})
    whitelist: List[str] = Field(default_factory=list, description="免催用户白名单", json_schema_extra={"label": "用户白名单（免催）", "hint": "列表中的用户不会被催促", "i18n": _schema_i18n(label_en="User Whitelist (Exempt)", label_ja="ユーザーホワイトリスト（免除）", placeholder_en="Enter user ID", placeholder_ja="ユーザーIDを入力"), "order": 1, "placeholder": "请输入用户ID"})
    group_whitelist: List[str] = Field(default_factory=list, description="免催群聊白名单", json_schema_extra={"label": "群聊白名单（免催）", "hint": "列表中的群聊不会触发催睡", "i18n": _schema_i18n(label_en="Group Whitelist (Exempt)", label_ja="グループホワイトリスト（免除）", placeholder_en="Enter group ID", placeholder_ja="グループIDを入力"), "order": 2, "placeholder": "输入免催群号"})


class NightmareConfig(PluginConfigBase):
    """配置大纲"""
    plugin: NightmarePluginSection = Field(default_factory=NightmarePluginSection)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    default_good_night: DefualtGoodNightConfig = Field(default_factory=DefualtGoodNightConfig)
    jam_reminder: JamReminderConfig = Field(default_factory=JamReminderConfig)


# ============================================================================
# 自定义 LLM Provider
# ============================================================================
class NightmareLLMProvider(LLMProviderBase):
    def __init__(self, plugin: 'NightmarePlugin'):
        self.plugin = plugin

    async def get_response(self, request: dict[str, Any]) -> dict[str, Any]:
        config = self.plugin.config.llm_config
        if not config.api_base or not config.api_key or not config.model_name:
            raise RuntimeError("LLM 提供商配置不完整")
        base = config.api_base.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {"Authorization": f"Bearer {config.api_key}", "Content-Type": "application/json"}
        messages = request.get("message_list")
        if not messages:
            raise ValueError("message_list is required")
        payload = {"model": config.model_name, "messages": messages, "temperature": config.temperature}
        if self.plugin._http_session is None or self.plugin._http_session.closed:
            self.plugin._http_session = aiohttp.ClientSession()
        async with self.plugin._http_session.post(url, json=payload, headers=headers, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HTTP {resp.status}: {text}")
            data = await resp.json()
            choices = data.get("choices", [])
            if not choices:
                raise RuntimeError("LLM 返回结果为空")
            return {"content": choices[0]["message"]["content"].strip()}


# ============================================================================
# 插件主体
# ============================================================================
class NightmarePlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已加载")
        self._last_interaction: Dict[str, float] = {}
        self._last_remind: Dict[str, float] = {}
        self._http_session: Optional[aiohttp.ClientSession] = None
        self.provider = NightmareLLMProvider(self)
        self._load_state()

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
        self._save_state()

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig

    @LLMProvider("1m.nightmare.provider", name="Nightmare LLM Provider", description="喊你睡觉插件自带的 OpenAI 兼容 LLM 提供商")
    async def handle_llm(self, operation: str, request: dict[str, Any]) -> dict[str, Any]:
        return await self.provider.dispatch(operation, request)

    # ===== 持久化辅助 =====
    def _get_state_file(self) -> str:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "nightmare_state.json")

    def _load_state(self) -> None:
        path = self._get_state_file()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._last_interaction = data.get("last_interaction", {})
                self._last_remind = data.get("last_remind", {})
                self.ctx.logger.info("[喊你睡觉] 已从文件恢复催睡状态")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] 加载状态文件失败: {e}")

    def _save_state(self) -> None:
        path = self._get_state_file()
        try:
            data = {"last_interaction": self._last_interaction, "last_remind": self._last_remind}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.ctx.logger.warning(f"[喊你睡觉] 保存状态文件失败: {e}")

    # ===== 辅助方法 =====
    def _enabled(self) -> bool:
        try:
            return bool(self.config.plugin.enabled)
        except Exception:
            return False

    def _get_user_id(self, message: dict) -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                uid = user_info.get("user_id", "")
                if uid: return str(uid)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            uid = user_info.get("user_id", "")
            if uid: return str(uid)
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            uid = sender.get("user_id", "")
            if uid: return str(uid)
        uid = message.get("user_id", "")
        if uid: return str(uid)
        raw = message.get("raw_message", {})
        if isinstance(raw, dict):
            sender = raw.get("sender", {})
            if isinstance(sender, dict):
                uid = sender.get("user_id", "")
                if uid: return str(uid)
            uid = raw.get("user_id", "")
            if uid: return str(uid)
        return ""

    def _get_group_id(self, message: dict) -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            group_info = message_info.get("group_info", {})
            if isinstance(group_info, dict):
                gid = group_info.get("group_id", "")
                if gid: return str(gid)
        gid = message.get("group_id", "")
        if gid: return str(gid)
        return ""

    def _get_platform(self, message: dict) -> str:
        platform = message.get("platform", "")
        if platform: return platform
        user_info = message.get("user_info", {})
        platform = user_info.get("platform", "")
        if platform: return platform
        message_info = message.get("message_info", {})
        platform = message_info.get("platform", "")
        if platform: return platform
        return "unknown"

    async def _get_user_name(self, message: dict, user_id: str = "", platform: str = "") -> str:
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                name = user_info.get("user_nickname") or user_info.get("nickname") or user_info.get("user_cardname") or user_info.get("user_name")
                if name: return str(name)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            name = user_info.get("user_nickname") or user_info.get("nickname") or user_info.get("user_name") or user_info.get("person_name")
            if name: return str(name)
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            name = sender.get("user_nickname") or sender.get("nickname") or sender.get("user_name") or sender.get("sender_name")
            if name: return str(name)
        name = message.get("user_nickname") or message.get("user_name") or message.get("sender_name")
        if name: return str(name)
        raw = message.get("raw_message", {})
        if isinstance(raw, dict):
            sender = raw.get("sender", {})
            if isinstance(sender, dict):
                name = sender.get("user_nickname") or sender.get("nickname") or sender.get("card") or sender.get("user_name")
                if name: return str(name)
        try:
            person_id = await self.ctx.person.get_id(platform, user_id)
            if person_id:
                nickname = await self.ctx.person.get_value(person_id, "nickname")
                if nickname: return str(nickname)
                person_name = await self.ctx.person.get_value(person_id, "person_name")
                if person_name: return str(person_name)
        except Exception:
            pass
        return "小伙伴"

    def _is_inside_remind_window(self, now: datetime.datetime) -> bool:
        try:
            config = self.config
            start_parts = config.scheduler.start_time.split(":")
            start_h = int(start_parts[0])
            start_m = int(start_parts[1])
            start_total = start_h * 60 + start_m
            end_total = (start_total + int(config.scheduler.sleep_hours * 60)) % (24 * 60)
            current_total = now.hour * 60 + now.minute
            if start_total <= end_total:
                return start_total <= current_total <= end_total
            else:
                return current_total >= start_total or current_total <= end_total
        except Exception:
            return False

    def _is_target_user(self, user_id: str) -> bool:
        try:
            config = self.config
            if config.jam_reminder.enable_jam_reminder:
                whitelist = config.jam_reminder.whitelist or []
                return user_id not in whitelist
            else:
                target = config.scheduler.target_user
                if not target:
                    return False
                return user_id == target
        except Exception:
            return False

    def _is_target_group(self, group_id: str) -> bool:
        if not group_id:
            return True
        config = self.config
        if not config.jam_reminder.enable_jam_reminder:
            return True
        group_whitelist = config.jam_reminder.group_whitelist or []
        if not group_whitelist:
            return True
        return group_id not in group_whitelist

    def _is_user_active(self, user_id: str) -> bool:
        last_interact = self._last_interaction.get(user_id, 0)
        if last_interact == 0:
            return False
        sleep_seconds = self.config.scheduler.sleep_hours * 3600
        return (time.time() - last_interact) <= sleep_seconds

    def _min_remind_interval_passed(self, user_id: str) -> bool:
        last_remind = self._last_remind.get(user_id, 0)
        if last_remind == 0:
            return True
        return (time.time() - last_remind) >= self.config.reminder.interval_seconds

    def _roll_probability(self) -> bool:
        prob = self.config.reminder.remind_probability
        if prob >= 1.0: return True
        if prob <= 0.0: return False
        return random.random() < prob

    def _get_name_probability(self, is_private: bool, user_id: str) -> float:
        """
        名字出现概率：
        - 私聊: 基础 0.8
        - 群聊(无差别): 基础 0.3
        - 间隔越短越低: min = 0.01
        最终概率 = max(base - interval_penalty, 0.01)
        """
        base = 0.8 if is_private else 0.3
        last_remind = self._last_remind.get(user_id, 0)
        if last_remind == 0:
            return base
        elapsed = time.time() - last_remind
        interval = self.config.reminder.interval_seconds
        penalty = max(0.0, (1.0 - elapsed / interval)) * (base - 0.01)
        return max(base - penalty, 0.01)

    async def _resolve_stream_id(self, message: dict, group_id: str) -> str:
        stream_id = message.get("stream_id") or message.get("session_id") or ""
        if stream_id:
            return stream_id
        if group_id:
            try:
                stream = await self.ctx.chat.get_stream_by_group_id(group_id, platform="qq")
                if isinstance(stream, dict):
                    stream_id = stream.get("stream_id") or stream.get("session_id") or ""
            except Exception:
                pass
        return stream_id

    # ===== 催睡执行 =====
    async def _do_remind(self, stream_id: str, user_name: str, platform: str, user_id: str, group_id: str = "", is_private: bool = False) -> None:
        config = self.config
        goodnight_text = config.default_good_night.default_good_night
        llm_model_used = "default"

        if config.llm_config.enable_llm:
            try:
                messages = await self.ctx.message.get_recent(chat_id=stream_id, limit=10)
                context_lines = []
                if messages and isinstance(messages, list):
                    for msg in messages[-5:]:
                        if not isinstance(msg, dict): continue
                        sender = msg.get("user_nickname") or msg.get("user_name") or msg.get("sender_name") or msg.get("user_id", "?")
                        text = msg.get("processed_plain_text") or msg.get("raw_message") or msg.get("content") or ""
                        if text and isinstance(text, str):
                            context_lines.append(f"{sender}: {text}")
                context = "\n".join(context_lines) if context_lines else "（暂无聊天记录）"
                now = datetime.datetime.now()
                # 使用用户在WebUI中配置的提示词，并追加隐藏要求
                prompt = (f"{config.llm_config.llm_text}\n"
                          f"平台：{platform}\n"
                          f"应该催睡的时间：{config.scheduler.start_time}，现在的时间：{now.strftime('%H:%M:%S')}\n"
                          f"回复内容不要携带任何引号。\n\n"
                          f"最近聊天记录：\n{context}")
                request_data = {"message_list": [{"role": "user", "content": prompt}]}
                response = await self.provider.get_response(request_data)
                goodnight_text = response.get("content", "").strip()
                # 额外去除可能遗留的引号
                goodnight_text = goodnight_text.strip('"''「」『』“”‘’')
                llm_model_used = config.llm_config.model_name or "custom"
                self.ctx.logger.info(f"[喊你睡觉] 自定义 LLM 生成成功，模型={llm_model_used}")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] 自定义 LLM 调用失败，回退默认文本: {e}")

        if not goodnight_text or not goodnight_text.strip():
            goodnight_text = "睡吧"

        # 插件自行决定是否添加昵称
        if goodnight_text:
            name_prob = self._get_name_probability(is_private, user_id)
            if random.random() < name_prob:
                if random.random() < 0.5:
                    goodnight_text = f"{user_name}，{goodnight_text}"
                else:
                    goodnight_text = f"{goodnight_text}，{user_name}"

        # 沉默模式：只记日志不发送
        if config.scheduler.silent_mode:
            now = datetime.datetime.now()
            target_info = f"群{group_id}" if group_id else "私聊"
            self.ctx.logger.info(
                f"[喊你睡觉]:喊你睡觉！ 沉默模式，未发送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
                f"平台{platform}，目标{target_info}，用户{user_name}({user_id})，"
                f"模型={llm_model_used}，来源=silent"
            )
            self._last_remind[user_id] = time.time()
            self._save_state()
            return

        # 正常发送
        self.ctx.logger.info(f"[喊你睡觉] 准备发送: stream_id={stream_id}, text={goodnight_text[:50]}")
        result = await self.ctx.send.text(goodnight_text, stream_id)
        self.ctx.logger.info(f"[喊你睡觉] 发送结果: {result}")

        self._last_remind[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        source = "custom" if config.llm_config.enable_llm else "default"
        target_info = f"群{group_id}" if group_id else "私聊"
        self.ctx.logger.info(
            f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"平台{platform}，目标{target_info}，用户{user_name}({user_id})，"
            f"模型={llm_model_used}，来源={source}，发送结果={result}，"
            f"聊天内容{goodnight_text[:50]}"
        )

    # ===== Hook =====
    @HookHandler(
        "chat.receive.after_process",
        name="nightmare_reminder",
        description="拦截消息并强制发送催睡",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        timeout_ms=5000,
    )
    async def handle_after_receive(self, message: dict, **kwargs) -> dict | None:
        del kwargs
        if not self._enabled():
            return None

        user_id = self._get_user_id(message)
        if not user_id:
            return None

        self._last_interaction[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        if not self._is_inside_remind_window(now):
            return None
        if not self._is_target_user(user_id):
            return None

        group_id = self._get_group_id(message)
        if not self._is_target_group(group_id):
            return None
        if not self._is_user_active(user_id):
            return None
        if not self._min_remind_interval_passed(user_id):
            return None
        if not self._roll_probability():
            self.ctx.logger.info(f"[喊你睡觉] 概率判定未通过，跳过催睡。概率={self.config.reminder.remind_probability}")
            return None

        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        stream_id = await self._resolve_stream_id(message, group_id)
        if not stream_id:
            self.ctx.logger.warning("[喊你睡觉] 无法解析 stream_id，放弃发送催睡")
            return None

        # 判断是否为私聊
        is_private = not bool(group_id)

        await self._do_remind(stream_id, user_name, platform, user_id, group_id, is_private)

        # 沉默模式下仍然拦截消息
        return {"action": "abort"}

    # ===== 事件处理器 =====
    @EventHandler("get_user_info", description="获取用户信息", event_type=EventType.ON_MESSAGE)
    async def on_user_message(self, message, **kwargs):
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        self.ctx.logger.info(f"[喊你睡觉] 用户消息: 平台={platform}, 用户={user_name}({user_id})")
        return {"intercepted": False}

    # ===== 命令处理器 =====
    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /nightmare 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)
        group_id = self._get_group_id(message)
        is_private = not bool(group_id)
        await self._do_remind(stream_id, user_name, platform, user_id, group_id, is_private)
        return True, "", True

    @Command("night", description="简单测试命令", pattern=r"^/night$")
    async def handle_nightmare_simple(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /night 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)
        group_id = self._get_group_id(message)
        now = datetime.datetime.now()
        remind_message = "晚安"
        await self.ctx.send.text(remind_message, stream_id)
        target_info = f"群{group_id}" if group_id else "私聊"
        self.ctx.logger.info(f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now}，平台{platform}，目标{target_info}，用户{user_name}，模型=N/A，来源=command，聊天内容{remind_message}")
        return True, "", True

    @Command("llmtest", description="测试独立LLM提供商连接", pattern=r"^/llmtest$")
    async def handle_llm_test(self, stream_id: str = "", **kwargs):
        config = self.config.llm_config
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /llmtest 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        if not config.enable_llm:
            await self.ctx.send.text("❌ 喊你睡觉 LLM 未启用", stream_id)
            return True, "LLM 未启用", 0
        try:
            test_request = {"message_list": [{"role": "user", "content": "请用中文回复'连接成功'，不要加任何其他内容。"}]}
            response = await self.provider.get_response(test_request)
            result = response.get("content", "")
            self.ctx.logger.info(f"[喊你睡觉] LLM 提供商测试成功，返回: {result}")
            await self.ctx.send.text(f"✅ 喊你睡觉 LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error(f"[喊你睡觉] LLM 提供商测试失败: {e}")
            await self.ctx.send.text(f"❌ 喊你睡觉 LLM 提供商测试失败: {e}", stream_id)
            return True, f"测试失败: {e}", 0

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)
        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(f"[喊你睡觉] /echo echo 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}")
            return True, "", True
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        await self.ctx.send.text(text, stream_id)
        return True, text, 1


def create_plugin():
    return NightmarePlugin()

# try25