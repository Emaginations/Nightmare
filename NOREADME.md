DeepSeek https://chat.deepseek.com
05-29 00:29:03 在讨论日志错误功能不生效时加入 深度思考 模式，try9 之前为默认模式（好像还开了智能搜索）

------------------------------------------------------------

"""
喊你睡觉：一个简单的催睡插件

2026-5-22 建立项目,尝试将WebUI配置中文本地化
2026-5-23 调整催睡时间设置的时间格式，添加睡眠时长sleep_hours
2026-5-24 增补readme.md，进行详细功能说明(设计),添加无差别催睡功能，默认关闭，新增白名单
2026-5-25 实现白名单的webui配置UI,添加用于测试的webui聊天用户名
2026-5-26 实现主体功能。用config = await self.ctx.config.get_plugin("com.example.my-plugin")尝试获取睡眠晚安插件的作息表
2026-5-28 正在测试
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
Q:[喊你睡觉]LLM调用异常: [E_CAPABILITY_DENIED] 插件 1m.nightmare 未获授权能力: message.get_recent??
A:_manifest.json 中需要添加权限
json

{
  "capabilities": [
    "send.text",
    "llm.generate",
    "message.get_recent",
    "message.build_readable",
    "chat.get_stream_by_user_id"
  ]
}
"""

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command, EventHandler, HookHandler
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType, HookMode, HookOrder
from typing import Dict, Optional, ClassVar, List
import asyncio
import random
import time
import datetime

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
        description="你睡觉的时长，低于这个时间间隔发言会被催睡，最低为4小时",
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
        description="提醒间隔（秒）",
        json_schema_extra={
            "label": "提醒间隔（秒）",
            "hint": "默认30秒，如果觉得太吵说明该睡觉了！",
            "i18n": _schema_i18n(
                label_en="Interval (seconds)",
                label_ja="間隔（秒）",
                hint_en="Time between two consecutive reminders.",
                hint_ja="連続するリマインダー間の時間。",
            ),
            "order": 0,
        },
    )

class LLMConfig(PluginConfigBase):
    """LLM提示词设置。"""
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
            "label": "白名单",
            "hint": "在这个列表里的一定都是夜猫无疑。",
            "i18n": _schema_i18n(
                label_en="Whitelist",
                label_ja="ホワイトリスト",
                hint_en="Users in this list will not be reminded when jam reminder is enabled.",
                hint_ja="無差別催促が有効な場合、このリスト内のユーザーは催促されません。",
                placeholder_en="Enter user ID",
                placeholder_ja="ユーザーIDを入力",
            ),
            "order": 1,
            "placeholder": "请输入用户ID",
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
# 插件主体
# ============================================================================
class NightmarePlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已加载")
        self._last_remind_time: Dict[str, float] = {}

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig

    # ===== 辅助方法 =====

    def _enabled(self) -> bool:
        try:
            return bool(self.config.plugin.enabled)
        except Exception:
            return False

    def _get_user_id(self, message: dict) -> str:
        """从消息中提取用户ID"""
        # 1. user_info
        user_info = message.get("user_info", {})
        user_id = user_info.get("user_id", "")
        if user_id:
            return str(user_id)

        # 2. sender
        sender = message.get("sender", {})
        user_id = sender.get("user_id", "")
        if user_id:
            return str(user_id)

        # 3. message 根层级
        user_id = message.get("user_id", "")
        if user_id:
            return str(user_id)

        # 4. message_info
        message_info = message.get("message_info", {})
        user_id = message_info.get("user_id", "")
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
        # 1. user_info
        user_info = message.get("user_info", {})
        user_name = (
            user_info.get("user_nickname")
            or user_info.get("nickname")
            or user_info.get("user_name")
            or user_info.get("person_name")
        )
        if user_name:
            return str(user_name)

        # 2. sender
        sender = message.get("sender", {})
        user_name = (
            sender.get("user_nickname")
            or sender.get("nickname")
            or sender.get("user_name")
            or sender.get("sender_name")
        )
        if user_name:
            return str(user_name)

        # 3. message 根层级
        user_name = (
            message.get("user_nickname")
            or message.get("user_name")
            or message.get("sender_name")
        )
        if user_name:
            return str(user_name)

        # 4. raw_message.sender (QQ napcat 格式)
        raw_message = message.get("raw_message", {})
        if isinstance(raw_message, dict):
            sender = raw_message.get("sender", {})
            if isinstance(sender, dict):
                user_name = (
                    sender.get("user_nickname")
                    or sender.get("nickname")
                    or sender.get("card")      # QQ 群名片
                    or sender.get("user_name")
                )
                if user_name:
                    return str(user_name)

        # 5. person API
        if user_id and platform and platform != "unknown":
            person_name = await self._get_user_name_from_person(platform, user_id)
            if person_name:
                return person_name

        # 6. 兜底
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

    def _interval_ok(self, user_id: str) -> bool:
        try:
            last_time = self._last_remind_time.get(user_id, 0)
            if last_time == 0:
                return True
            sleep_seconds = self.config.scheduler.sleep_hours * 3600
            return (time.time() - last_time) > sleep_seconds
        except Exception:
            return False

    async def _do_remind(self, stream_id: str, user_name: str, platform: str, user_id: str) -> None:
        """执行催睡"""
        config = self.config
        goodnight_text = config.default_good_night.default_good_night

        # LLM 模式
        if config.llm_config.enable_llm:
            try:
                # 获取聊天流最近消息
                messages = await self.ctx.message.get_recent(
                    chat_id=stream_id,
                    limit=10,
                )

                # 手动构建上下文
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

                # 使用默认模型配置（走 WebUI 中插件任务设置）
                result = await self.ctx.llm.generate(prompt=prompt)
                if result.get("success") and result.get("response"):
                    goodnight_text = result["response"].strip()
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] LLM 生成失败，使用默认文本: {e}")

        if not goodnight_text or not goodnight_text.strip():
            goodnight_text = "睡吧"

        # 发送
        await self.ctx.send.text(goodnight_text, stream_id)
        self._last_remind_time[user_id] = time.time()

        now = datetime.datetime.now()
        self.ctx.logger.info(
            f"[喊你睡觉]:已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"平台{platform}，用户{user_name}({user_id})，"
            f"聊天内容{goodnight_text[:50]}"
        )

    # ===== Hook =====

    @HookHandler(
        "chat.receive.after_process",
        name="nightmare_reminder",
        description="每条消息到达后检测催睡条件",
        mode=HookMode.OBSERVE,
        order=HookOrder.LATE,
    )
    async def handle_after_receive(self, message: dict, **kwargs) -> None:
        del kwargs

        if not self._enabled():
            return

        # 调试：打印完整 message 结构（前500字符）
        self.ctx.logger.info(f"[喊你睡觉] DEBUG 完整 message: {str(message)[:500]}")

        user_id = self._get_user_id(message)
        if not user_id:
            self.ctx.logger.info(f"[喊你睡觉] DEBUG 未能提取 user_id，message keys: {list(message.keys())}")
            return

        now = datetime.datetime.now()

        if not self._is_inside_remind_window(now):
            return
        if not self._interval_ok(user_id):
            return
        if not self._is_target_user(user_id):
            return

        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        stream_id = message.get("stream_id", "")

        await self._do_remind(stream_id, user_name, platform, user_id)

    # ===== 事件处理器 =====

    @EventHandler(
        "get_user_info",
        description="获取用户信息",
        event_type=EventType.ON_MESSAGE,
    )
    async def on_user_message(self, message, **kwargs):
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)

        self.ctx.logger.info(
            f"[喊你睡觉] 用户消息: 平台={platform}, 用户={user_name}({user_id})"
        )
        return {"intercepted": False}

    # ===== 命令 =====

    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        # try9 - nightmare test command
        message = kwargs.get("message", {})
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)

        await self._do_remind(stream_id, user_name, platform, user_id)

        return True, f"已向{user_name}发送催睡测试", True

    @Command("night", description="简单测试命令", pattern=r"^/night$")
    async def handle_nightmare_simple(self, stream_id: str = "", **kwargs):
        message = kwargs.get("message", {})
        user_id = self._get_user_id(message)
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)

        now = datetime.datetime.now()
        remind_message = "晚安"

        await self.ctx.send.text(remind_message, stream_id)

        self.ctx.logger.info(
            f"[喊你睡觉]:已推送催睡，时间{now}，"
            f"平台{platform}，用户{user_name}，聊天内容{remind_message}"
        )

        return True, f"已向{user_name}发送催睡测试", True

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1


def create_plugin():
    return NightmarePlugin()

# try10

############构建过程参见NOREADME.md############
*检查一下现在的所有代码并输出try11，顺便帮我在readme里添加关于webui测试账户的说明：
# 喊你睡觉(Nightmare)

## 简介

这是一个到达设定时间点后，无论什么地方，只要你出现了麦麦就会喊你去睡觉的插件。主项目是[maibot](https://github.com/Mai-with-u/MaiBot)。

<br>

## 项目状态

### ✅写完了

### ⚠️正在测试

<br>

## 配置

有人性化的webui设计，请在webui插件市场安装并在管理页面进行配置:

<br>

### 插件开关

使能插件。

<br>

### 催睡设置

在这里设定催促对象(qq号或者微信号)、开始催促的时间、睡眠时长。

#### 睡眠时长

设定你睡觉的时长，低于这个时间间隔发言会被继续催促，直到两次出现的间隔大于这里设定的时长。

<br>

### LLM提示词设置

在这里设置是否根据跟据上下文生成喊你睡觉的话，会消耗更多的token，但会显得更加自然。

<br>

### 无差别催睡

默认关闭。开启后会无差别地催促所有人，包括你自己。

#### 白名单

开启无差别催睡后，白名单中的用户不会被催促。(在这个列表里的一定都是夜猫无疑。)

<br>

## 测试

在webui建立聊天,发送"/nightmare"触发测试，
如果看到maibot日志显示[喊你睡觉]:已推送催睡，时间...，昵称...，聊天内容...，并收到晚安消息，则说明测试成功。
如果同时安装了晚安睡眠管理插件，会在插件加载时显示[喊你睡觉]:已读取晚安睡眠管理插件配置，入睡时间...。

<br>

## 注意

#### 请确保maibot版本为1.0.0pre24或以上,否则webui可能无法正确显示中文插件配置。

#### 兼容晚安睡眠管理插件，会在晚安后继续催睡。如果安装了晚安睡眠管理插件会自动读取已经设定的作息时间。(未实装)

#### 其他语言翻译没有经过仔细审核。