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
2026-6-10 try21: 新增群聊白名单；改为 BLOCKING Hook 拦截消息并直接发送催睡，不经过 Maisaka 循环
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
    """构造 WebUI 配置项多语言说明，保留外层中文字段兼容旧格式。"""

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

    enabled: bool = Field(
        default=False,
        description="是否启用喊你睡觉插件",
        json_schema_extra={
            "label": "开关",
            "i18n": _schema_i18n(
                label_en="Enable",
                label_ja="アダプターを有効化",
            ),
            "order": 0,
        },
    )
    config_version: str = Field(
        default="2.0.0",
        description="配置版本",
        json_schema_extra={
            "label": "配置版本",
            "i18n": _schema_i18n(
                label_en="Config version",
                label_ja="設定バージョン",
                hint_en="Configuration version number.",
                hint_ja="設定のバージョン番号。",
            ),
            "order": 1,
        },
    )


class SchedulerConfig(PluginConfigBase):
    """催睡时间设置。"""

    __ui_label__: ClassVar[str] = "催睡时间"
    __ui_order__: ClassVar[int] = 1

    # 催睡对象
    target_user: str = Field(
        default="",
        description="催促对象（QQ号、微信号或其他平台用户ID）",
        json_schema_extra={
            "label": "催促对象",
            "hint": "在这里设定催促对象（QQ号、微信号或其他平台用户ID）",
            "placeholder": "请输入用户ID",
            "i18n": _schema_i18n(
                label_en="Target user",
                label_ja="催促対象",
                hint_en="Set the target user to remind (QQ ID, WeChat ID, or other platform user ID). Leave empty to remind no one.",
                hint_ja="催促する対象を設定します（QQ ID、WeChat ID、またはその他のプラットフォームのユーザーID）。空の場合は誰も催促しません。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザーIDを入力",
            ),
            "order": 0,
        },
    )

    test_user: str = Field(
        default="WebUI用户",
        description="用于从webUI测试，默认用户名为：WebUI用户",
        json_schema_extra={
            "label": "webui聊天用户名",
            "hint": "用于测试，用户名位于webui聊天室左下角，默认为：WebUI用户名",
            "i18n": _schema_i18n(
                label_en="WebUI chat username",
                label_ja="WebUIチャットユーザー名",
                hint_en="Located in the bottom left corner of the WebUI chat room. Default: WebUI Username. For testing only.",
                hint_ja="WebUIチャットルームの左下隅に表示されます。デフォルト：WebUIユーザー名。テスト専用。",
                placeholder_en="Enter WebUI username",
                placeholder_ja="WebUIユーザー名を入力",
            ),
            "placeholder": "WebUI用户",
            "order": 0,
        },
    )

    webui_only_commands: bool = Field(
        default=True,
        description="是否只有WebUI聊天可以触发 /night 和 /nightmare 命令",
        json_schema_extra={
            "label": "命令仅限WebUI",
            "hint": "开启后，/night 和 /nightmare 命令仅在WebUI聊天中可用，其他平台会提示不可用。",
            "i18n": _schema_i18n(
                label_en="Commands only in WebUI",
                label_ja="コマンドはWebUIのみ",
                hint_en="When enabled, /night and /nightmare commands are only available in WebUI chat.",
                hint_ja="有効にすると、/night と /nightmare コマンドはWebUIチャットでのみ使用できます。",
            ),
            "order": 1,
        },
    )

    start_time: str = Field(
        default="22:00",
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="催睡开始时间（格式 HH:MM，例如 22:00）",
        json_schema_extra={
            "label": "开始时间",
            "placeholder": "22:00",
            "i18n": _schema_i18n(
                label_en="Start time",
                label_ja="開始時間",
                hint_en="Bedtime reminder start time (format HH:MM, e.g., 22:00).",
                hint_ja="就寝リマインダー開始時間（形式 HH:MM、例：22:00）。",
            ),
            "order": 1,
        },
    )

    # 睡眠时长：4-12小时，步进1小时
    sleep_hours: float = Field(
        default=8,
        ge=4,
        le=12,
        description="你睡觉的时长，低于这个时间间隔发言会被继续催促，最低为4小时",
        json_schema_extra={
            "label": "睡眠时长（小时）",
            "hint": "你睡觉的时长，低于这个时间间隔发言会被催睡，最低为4小时",
            "x-widget": "slider",
            "min": 4,
            "max": 12,
            "step": 0.5,
            "i18n": _schema_i18n(
                label_en="Sleep hours",
                label_ja="睡眠時間（時間）",
                hint_en="Your sleep duration. Reminders will continue if the interval is less than this value. Minimum is 4 hours.",
                hint_ja="あなたの睡眠時間。この時間より間隔が短い場合、リマインダーは続行されます。最低は4時間です。",
            ),
            "order": 2,
        },
    )

    # 辅助方法：获取小时
    @property
    def start_hour(self) -> int:
        return int(self.start_time.split(":")[0])

    # 辅助方法：获取分钟
    @property
    def start_minute(self) -> int:
        return int(self.start_time.split(":")[1])

    # 辅助方法：获取总分钟数
    @property
    def total_start_minutes(self) -> int:
        return self.start_hour * 60 + self.start_minute

    # 辅助方法：判断当前时间是否应该催睡
    def should_remind(self, current_hour: int, current_minute: int) -> bool:
        """判断当前时间是否应该触发催睡"""
        current_total = current_hour * 60 + current_minute
        return current_total >= self.total_start_minutes

        
class ReminderConfig(PluginConfigBase):
    """提醒频率与重复设置。"""

    __ui_label__: ClassVar[str] = "提醒设置"
    __ui_order__: ClassVar[int] = 2

    interval_seconds: int = Field(
        default=30,
        ge=5,
        le=120,
        description="两次催睡之间的最小间隔（秒）",
        json_schema_extra={
            "label": "提醒间隔（秒）",
            "hint": "默认30秒，防止短时间内重复催睡",
            "i18n": _schema_i18n(
                label_en="Interval (seconds)",
                label_ja="間隔（秒）",
                hint_en="Minimum interval between two reminders.",
                hint_ja="連続するリマインダー間の最小時間。",
            ),
            "order": 0,
        },
    )

    # 催睡概率：0-1，默认1，步进0.01
    remind_probability: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="满足其他催睡条件时，实际触发催睡的概率。1表示总是催睡，0表示从不催睡。",
        json_schema_extra={
            "label": "催睡概率",
            "hint": "设置0到1之间的数值，表示满足催睡条件后实际发送消息的概率。1为始终触发，0为永不触发。",
            "x-widget": "slider",
            "min": 0,
            "max": 1,
            "step": 0.01,
            "i18n": _schema_i18n(
                label_en="Remind probability",
                label_ja="リマインド確率",
                hint_en="Probability (0-1) to actually send the reminder when conditions are met. 1 = always, 0 = never.",
                hint_ja="条件が満たされたときに実際にリマインダーを送信する確率（0～1）。1=常に送信、0=送信しない。",
            ),
            "order": 1,
        },
    )

class LLMConfig(PluginConfigBase):
    """LLM提示词设置（独立提供商，不依赖主程序模型）"""
    __ui_label__: ClassVar[str] = "LLM提示词设置"
    __ui_order__: ClassVar[int] = 3

    enable_llm: bool = Field(
        default=True,
        description="是否启用LLM跟据上下文生成催促你睡觉的话",
        json_schema_extra={
            "label": "是否启用LLM",
            "hint": "是否启用LLM跟据上下文生成催促你睡觉的话",
            "i18n": _schema_i18n(
                label_en="Enable LLM",
                label_ja="LLMを有効にする",
                hint_en="Whether to enable LLM.",
                hint_ja="LLMを有効にするかどうか。",
            ),
            "order": 0,
        },
    )

    llm_text: str = Field(
        default="请根据当前上下文生成一句催促某人去睡觉的话",
        description="LLM提示词",
        json_schema_extra={
            "label": "LLM提示词",
            "hint": "默认：请根据当前上下文生成一句催促某人去睡觉的话",
            "i18n": _schema_i18n(
                label_en="LLM prompt",
                label_ja="LLMプロンプト",
                hint_en="defualt: Just go to sleep",
                hint_ja="初期設定:寝て"
            ),
            "order": 1,
        },
    )

    # ---------- 独立 LLM 提供商配置 ----------
    api_base: str = Field(
        default="https://api.deepseek.com",
        description="API 地址（OpenAI 兼容格式，例如 https://api.deepseek.com）",
        json_schema_extra={
            "label": "API 地址",
            "hint": "默认使用 DeepSeek API：https://api.deepseek.com",
            "placeholder": "https://api.deepseek.com",
            "i18n": _schema_i18n(
                label_en="API Base URL",
                label_ja="APIベースURL",
                hint_en="Default: DeepSeek API https://api.deepseek.com",
                hint_ja="デフォルト：DeepSeek API https://api.deepseek.com",
                placeholder_en="https://api.deepseek.com",
                placeholder_ja="https://api.deepseek.com",
            ),
            "order": 2,
        },
    )
    api_key: str = Field(
        default="",
        description="API 密钥",
        json_schema_extra={
            "label": "API 密钥",
            "hint": "Bearer Token 或 API Key",
            "placeholder": "sk-...",
            "i18n": _schema_i18n(
                label_en="API Key",
                label_ja="APIキー",
                hint_en="Your API key.",
                hint_ja="APIキーを入力してください。",
                placeholder_en="sk-...",
                placeholder_ja="sk-...",
            ),
            "order": 3,
        },
    )
    model_name: str = Field(
        default="deepseek-chat",
        description="模型名称",
        json_schema_extra={
            "label": "模型名称",
            "hint": "例如 deepseek-chat, deepseek-reasoner",
            "placeholder": "deepseek-chat",
            "i18n": _schema_i18n(
                label_en="Model Name",
                label_ja="モデル名",
                hint_en="e.g. deepseek-chat",
                hint_ja="例：deepseek-chat",
                placeholder_en="deepseek-chat",
                placeholder_ja="deepseek-chat",
            ),
            "order": 4,
        },
    )
    temperature: float = Field(
        default=0.8,
        ge=0.0,
        le=2.0,
        description="生成温度，控制随机性。0-2，默认0.8",
        json_schema_extra={
            "label": "温度 (Temperature)",
            "hint": "较高的值如 0.8 会使输出更随机，较低的值如 0.2 会使其更集中和确定。",
            "x-widget": "slider",
            "min": 0.0,
            "max": 2.0,
            "step": 0.1,
            "i18n": _schema_i18n(
                label_en="Temperature",
                label_ja="温度",
                hint_en="Higher values like 0.8 will make the output more random, while lower values like 0.2 will make it more focused and deterministic.",
                hint_ja="0.8などの高い値は出力をよりランダムにし、0.2などの低い値はより集中的で決定論的にします。",
            ),
            "order": 5,
        },
    )

class DefualtGoodNightConfig(PluginConfigBase):
    """默认晚安设置。"""
    __ui_label__: ClassVar[str] = "默认晚安设置"
    __ui_order__: ClassVar[int] = 4

    default_good_night: str = Field(
        default="睡吧",
        description="喊你睡觉",
        json_schema_extra={
            "label": "默认晚安",
            "hint": "睡吧",
            "i18n": _schema_i18n(
                label_en="Default good night",
                label_ja="デフォルトの夜寝",
                hint_en="Default good night",
                hint_ja="デフォルトの夜寝",
            ),
            "order": 0,
        },
    )

class JamReminderConfig(PluginConfigBase):
    """无差别催睡配置"""
    
    __ui_label__: ClassVar[str] = "无差别催睡"
    __ui_order__: ClassVar[int] = 5

    enable_jam_reminder: bool = Field(
        default=False,
        description="是否启用无差别催睡。开启后会无差别地催促所有人，包括你自己。",
        json_schema_extra={
            "label": "启用无差别催睡",
            "hint": "开启后会无差别地催促所有人，包括你自己。",
            "i18n": _schema_i18n(
                label_en="Enable Jam Reminder",
                label_ja="無差別催促を有効にする",
                hint_en="When enabled, everyone will be reminded indiscriminately, including yourself.",
                hint_ja="有効にすると、自分を含む全員が無差別に催促されます。",
            ),
            "order": 0,
        },
    )

    whitelist: List[str] = Field(
        default_factory=list,
        description="无差别催睡白名单。开启无差别催睡后，白名单中的用户不会被催促。",
        json_schema_extra={
            "label": "用户白名单",
            "hint": "在这个列表里的一定都是夜猫无疑。",
            "i18n": _schema_i18n(
                label_en="User Whitelist",
                label_ja="ユーザーホワイトリスト",
                hint_en="Users in this list will not be reminded when jam reminder is enabled.",
                hint_ja="無差別催促が有効な場合、このリスト内のユーザーは催促されません。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザーIDを入力",
            ),
            "order": 1,
            "placeholder": "请输入用户ID",
        },
    )

    # 新增：群聊白名单
    group_whitelist: List[str] = Field(
        default_factory=list,
        description="无差别催睡群聊白名单。仅在列表中的群聊才会触发催睡，留空表示所有群聊。",
        json_schema_extra={
            "label": "群聊白名单",
            "hint": "只在列表中的群聊触发催睡；留空则所有群聊均可触发。",
            "i18n": _schema_i18n(
                label_en="Group Whitelist",
                label_ja="グループホワイトリスト",
                hint_en="Only groups in this list will trigger reminders when jam reminder is enabled. Leave empty for all groups.",
                hint_ja="無差別催促が有効な場合、このリスト内のグループのみリマインダーをトリガーします。空の場合はすべてのグループ。",
                placeholder_en="Enter group ID",
                placeholder_ja="グループIDを入力",
            ),
            "order": 2,
            "placeholder": "请输入群号",
        },
    )

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
    """喊你睡觉插件专用的 LLM Provider，提供 OpenAI 兼容的 response 能力。"""
    def __init__(self, plugin: 'NightmarePlugin'):
        self.plugin = plugin

    async def get_response(self, request: dict[str, Any]) -> dict[str, Any]:
        config = self.plugin.config.llm_config
        if not config.api_base or not config.api_key or not config.model_name:
            raise RuntimeError("LLM 提供商配置不完整，请检查 API 地址、密钥和模型名称")
        base = config.api_base.rstrip("/")
        url = f"{base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        messages = request.get("message_list")
        if not messages:
            raise ValueError("message_list is required")
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
        }
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
            content = choices[0]["message"]["content"].strip()
            return {"content": content}


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
            data = {
                "last_interaction": self._last_interaction,
                "last_remind": self._last_remind,
            }
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
        """从消息中提取用户ID"""
        # 1. message_info.user_info (QQ 实际结构)
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                user_id = user_info.get("user_id", "")
                if user_id:
                    return str(user_id)

        # 2. user_info (顶层)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            user_id = user_info.get("user_id", "")
            if user_id:
                return str(user_id)

        # 3. sender
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            user_id = sender.get("user_id", "")
            if user_id:
                return str(user_id)

        # 4. message 根层级
        user_id = message.get("user_id", "")
        if user_id:
            return str(user_id)

        # 5. raw_message 嵌套 sender
        raw_message = message.get("raw_message", {})
        if isinstance(raw_message, dict):
            sender = raw_message.get("sender", {})
            if isinstance(sender, dict):
                user_id = sender.get("user_id", "")
                if user_id:
                    return str(user_id)

        # 6. raw_message 直接取 user_id
        if isinstance(raw_message, dict):
            user_id = raw_message.get("user_id", "")
            if user_id:
                return str(user_id)

        return ""

    def _get_group_id(self, message: dict) -> str:
        """提取群聊ID，若非群聊返回空字符串"""
        # message_info.group_info
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            group_info = message_info.get("group_info", {})
            if isinstance(group_info, dict):
                group_id = group_info.get("group_id", "")
                if group_id:
                    return str(group_id)
        # 顶层 group_id
        group_id = message.get("group_id", "")
        if group_id:
            return str(group_id)
        return ""

    def _get_platform(self, message: dict) -> str:
        platform = message.get("platform", "")
        if platform:
            return platform

        user_info = message.get("user_info", {})
        platform = user_info.get("platform", "")
        if platform:
            return platform

        message_info = message.get("message_info", {})
        platform = message_info.get("platform", "")
        if platform:
            return platform

        return "unknown"

    async def _get_user_name_from_person(self, platform: str, user_id: str) -> str:
        """通过 person API 获取用户名"""
        try:
            person_id = await self.ctx.person.get_id(platform, user_id)
            if not person_id:
                return ""

            nickname = await self.ctx.person.get_value(person_id, "nickname")
            if nickname:
                return str(nickname)

            person_name = await self.ctx.person.get_value(person_id, "person_name")
            if person_name:
                return str(person_name)

            return ""
        except Exception as e:
            self.ctx.logger.debug(f"[喊你睡觉] person API 查询失败: {e}")
            return ""

    async def _get_user_name(self, message: dict, user_id: str = "", platform: str = "") -> str:
        """从消息中提取用户名"""
        # 1. message_info.user_info (QQ 实际结构)
        message_info = message.get("message_info", {})
        if isinstance(message_info, dict):
            user_info = message_info.get("user_info", {})
            if isinstance(user_info, dict):
                user_name = (
                    user_info.get("user_nickname")
                    or user_info.get("nickname")
                    or user_info.get("user_cardname")
                    or user_info.get("user_name")
                )
                if user_name:
                    return str(user_name)

        # 2. user_info (顶层)
        user_info = message.get("user_info", {})
        if isinstance(user_info, dict):
            user_name = (
                user_info.get("user_nickname")
                or user_info.get("nickname")
                or user_info.get("user_name")
                or user_info.get("person_name")
            )
            if user_name:
                return str(user_name)

        # 3. sender
        sender = message.get("sender", {})
        if isinstance(sender, dict):
            user_name = (
                sender.get("user_nickname")
                or sender.get("nickname")
                or sender.get("user_name")
                or sender.get("sender_name")
            )
            if user_name:
                return str(user_name)

        # 4. message 根层级
        user_name = (
            message.get("user_nickname")
            or message.get("user_name")
            or message.get("sender_name")
        )
        if user_name:
            return str(user_name)

        # 5. raw_message.sender (QQ napcat 备用)
        raw_message = message.get("raw_message", {})
        if isinstance(raw_message, dict):
            sender = raw_message.get("sender", {})
            if isinstance(sender, dict):
                user_name = (
                    sender.get("user_nickname")
                    or sender.get("nickname")
                    or sender.get("card")
                    or sender.get("user_name")
                )
                if user_name:
                    return str(user_name)

        # 6. person API 兜底
        if user_id and platform and platform != "unknown":
            person_name = await self._get_user_name_from_person(platform, user_id)
            if person_name:
                return person_name

        return "小伙伴"

    def _is_inside_remind_window(self, now: datetime.datetime) -> bool:
        try:
            config = self.config
            start_parts = config.scheduler.start_time.split(":")
            start_total = int(start_parts[0]) * 60 + int(start_parts[1])
            current_total = now.hour * 60 + now.minute
            return current_total >= start_total
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
        """检查群聊是否在催睡范围内（仅当开启无差别催睡且群聊白名单非空时生效）"""
        if not group_id:
            return True  # 私聊不受限制
        config = self.config
        if not config.jam_reminder.enable_jam_reminder:
            return True  # 特定用户模式不限制群聊
        group_whitelist = config.jam_reminder.group_whitelist or []
        if not group_whitelist:
            return True  # 未设置群聊白名单则允许所有群聊
        return group_id in group_whitelist

    def _is_user_active(self, user_id: str) -> bool:
        """用户是否仍在熬夜期（最后互动距现在 <= sleep_hours）"""
        last_interact = self._last_interaction.get(user_id, 0)
        if last_interact == 0:
            return False
        sleep_seconds = self.config.scheduler.sleep_hours * 3600
        return (time.time() - last_interact) <= sleep_seconds

    def _min_remind_interval_passed(self, user_id: str) -> bool:
        """距离上次催睡是否已超过最小间隔"""
        last_remind = self._last_remind.get(user_id, 0)
        if last_remind == 0:
            return True
        interval = self.config.reminder.interval_seconds
        return (time.time() - last_remind) >= interval

    def _roll_probability(self) -> bool:
        """根据催睡概率决定本次是否触发"""
        prob = self.config.reminder.remind_probability
        if prob >= 1.0:
            return True
        if prob <= 0.0:
            return False
        return random.random() < prob

    async def _do_remind(self, stream_id: str, user_name: str, platform: str, user_id: str) -> None:
        """执行催睡，包含 LLM 调用与日志"""
        config = self.config
        goodnight_text = config.default_good_night.default_good_night
        llm_model_used = "default"

        if config.llm_config.enable_llm:
            try:
                messages = await self.ctx.message.get_recent(
                    chat_id=stream_id,
                    limit=10,
                )
                context_lines = []
                if messages and isinstance(messages, list):
                    for msg in messages[-5:]:
                        if not isinstance(msg, dict):
                            continue
                        sender = (
                            msg.get("user_nickname")
                            or msg.get("user_name")
                            or msg.get("sender_name")
                            or msg.get("user_id", "?")
                        )
                        text = (
                            msg.get("processed_plain_text")
                            or msg.get("raw_message")
                            or msg.get("content")
                            or ""
                        )
                        if text and isinstance(text, str):
                            context_lines.append(f"{sender}: {text}")

                context = "\n".join(context_lines) if context_lines else "（暂无聊天记录）"
                prompt = f"{config.llm_config.llm_text}\n用户昵称：{user_name}\n平台：{platform}\n\n最近聊天记录：\n{context}"

                request_data = {
                    "message_list": [{"role": "user", "content": prompt}]
                }
                response = await self.provider.get_response(request_data)
                goodnight_text = response.get("content", "").strip()
                llm_model_used = config.llm_config.model_name or "custom"
                self.ctx.logger.info(f"[喊你睡觉] 自定义 LLM 生成成功，模型={llm_model_used}")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] 自定义 LLM 调用失败，回退默认文本: {e}")

        if not goodnight_text or not goodnight_text.strip():
            goodnight_text = "睡吧"

        await self.ctx.send.text(goodnight_text, stream_id)
        self._last_remind[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        source = "custom" if config.llm_config.enable_llm else "default"
        self.ctx.logger.info(
            f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"平台{platform}，用户{user_name}({user_id})，"
            f"模型={llm_model_used}，来源={source}，"
            f"聊天内容{goodnight_text[:50]}"
        )

    # ===== Hook：BLOCKING 拦截消息，直接发送催睡 =====

    @HookHandler(
        "chat.receive.after_process",
        name="nightmare_reminder",
        description="拦截消息进行催睡",
        mode=HookMode.BLOCKING,   # 改为 BLOCKING，可 abort 消息
        order=HookOrder.LATE,
        timeout_ms=5000,
    )
    async def handle_after_receive(self, message: dict, **kwargs) -> dict | None:
        """收到消息后检查是否需要催睡，若触发则发送催睡并拦截原消息"""
        del kwargs

        if not self._enabled():
            return None

        user_id = self._get_user_id(message)
        if not user_id:
            self.ctx.logger.debug("[喊你睡觉] 未能提取 user_id，跳过")
            return None

        # 更新互动时间
        self._last_interaction[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        # 1. 时间窗口
        if not self._is_inside_remind_window(now):
            return None

        # 2. 目标用户
        if not self._is_target_user(user_id):
            return None

        # 3. 群聊白名单检查
        group_id = self._get_group_id(message)
        if not self._is_target_group(group_id):
            self.ctx.logger.debug(f"[喊你睡觉] 群 {group_id} 不在群聊白名单中，跳过")
            return None

        # 4. 活跃度 (sleep_hours timegate)
        if not self._is_user_active(user_id):
            self.ctx.logger.debug(f"[喊你睡觉] 用户 {user_id} 已沉默超过睡眠时长，不再催睡")
            return None

        # 5. 最小间隔
        if not self._min_remind_interval_passed(user_id):
            return None

        # 6. 概率
        if not self._roll_probability():
            self.ctx.logger.info(f"[喊你睡觉] 概率判定未通过，跳过催睡。概率={self.config.reminder.remind_probability}")
            return None

        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        stream_id = message.get("stream_id", "")

        # 发送催睡消息
        await self._do_remind(stream_id, user_name, platform, user_id)

        # 拦截当前消息，阻止 Maisaka 继续处理
        return {"action": "abort"}

    # ===== 事件处理器 =====

    @EventHandler(
        "get_user_info",
        description="获取用户信息",
        event_type=EventType.ON_MESSAGE,
    )
    async def on_user_message(self, message, **kwargs):
        """获取用户信息并记录互动时间"""
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)

        self.ctx.logger.info(
            f"[喊你睡觉] 用户消息: 平台={platform}, 用户={user_name}({user_id})"
        )
        return {"intercepted": False}

    # ===== 命令处理器 =====

    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        # try21 - nightmare test command (强制触发，不拦截)
        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(
                f"[喊你睡觉] /nightmare 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}"
            )
            return True, "", True

        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)

        await self._do_remind(stream_id, user_name, platform, user_id)
        return True, "", True

    @Command("night", description="简单测试命令", pattern=r"^/night$")
    async def handle_nightmare_simple(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        platform = self._get_platform(message)

        if self.config.scheduler.webui_only_commands and platform != "webui":
            self.ctx.logger.info(
                f"[喊你睡觉] /night 命令在非WebUI平台被触发，已忽略。平台={platform}, stream_id={stream_id}"
            )
            return True, "", True

        user_id = self._get_user_id(message)
        user_name = await self._get_user_name(message, user_id, platform)

        now = datetime.datetime.now()
        remind_message = "晚安"
        await self.ctx.send.text(remind_message, stream_id)

        self.ctx.logger.info(
            f"[喊你睡觉]:喊你睡觉！ 已推送催睡，时间{now}，"
            f"平台{platform}，用户{user_name}，模型=N/A，来源=command，"
            f"聊天内容{remind_message}"
        )
        return True, "", True

    @Command("llmtest", description="测试独立LLM提供商连接", pattern=r"^/llmtest$")
    async def handle_llm_test(self, stream_id: str = "", **kwargs):
        config = self.config.llm_config
        if not config.enable_llm:
            await self.ctx.send.text("❌ LLM 未启用", stream_id)
            return True, "LLM 未启用", 0

        try:
            test_request = {
                "message_list": [{"role": "user", "content": "请用中文回复'连接成功'，不要加任何其他内容。"}]
            }
            response = await self.provider.get_response(test_request)
            result = response.get("content", "")
            self.ctx.logger.info(f"[喊你睡觉] LLM 提供商测试成功，返回: {result}")
            await self.ctx.send.text(f"✅ LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error(f"[喊你睡觉] LLM 提供商测试失败: {e}")
            await self.ctx.send.text(f"❌ LLM 提供商测试失败: {e}", stream_id)
            return True, f"测试失败: {e}", 0

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1


def create_plugin():
    return NightmarePlugin()

# try21