"""
喊你睡觉：一个简单的催睡插件

2026-5-22 建立项目,尝试将WebUI配置中文本地化
2026-5-23 调整催睡时间设置的时间格式，添加睡眠时长sleep_hours
2026-5-24 增补readme.md，进行详细功能说明(设计),添加无差别催睡功能，默认关闭，新增白名单
2026-5-25 实现白名单的webui配置UI,添加用于测试的webui聊天用户名
2026-5-26 实现主体功能。用config = await self.ctx.config.get_plugin("com.example.my-plugin")尝试获取睡眠晚安插件的作息表
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
            "hint": "用户名位于webui聊天室左下角，默认为：WebUI用户名",
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
        default=False,
        description="是否启用LLM跟据上下文生成喊你睡觉的话",
        json_schema_extra={
            "label": "是否启用LLM",
            "hint": "是否启用LLM跟据上下文生成喊你睡觉的话",
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
        # 初始化最后提醒时间字典
        self._last_remind_time: Dict[str, float] = {}

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig

    # ===== 工具方法 =====
    
    @Tool(
        "check_sleep_time",
        brief_description="检查是否应该催睡",
        detailed_description="检查当前时间是否在设定的入睡时间之后，以及与用户的上一次互动是否超过睡眠时长。"
                           "参数说明：\n- user_id：string，必填。要检查的用户ID。",
        parameters=[
            ToolParameterInfo(
                name="user_id",
                param_type=ToolParamType.STRING,
                description="用户ID",
                required=True,
            ),
        ],
    )
    async def check_sleep_time(self, user_id: str, **kwargs):
        """检查是否应该催睡：时间条件 + 互动间隔条件"""
        config = self.config_model
        
        # 获取当前时间（datetime.now()返回datetime对象，格式与配置不同）
        now = datetime.datetime.now()
        current_hour = now.hour
        current_minute = now.minute
        
        # 解析配置中的入睡时间（格式：HH:MM）
        start_time_parts = config.scheduler.start_time.split(":")
        start_hour = int(start_time_parts[0])
        start_minute = int(start_time_parts[1])
        
        # 检查时间条件：当前时间是否在入睡时间之后
        current_total_minutes = current_hour * 60 + current_minute
        start_total_minutes = start_hour * 60 + start_minute
        
        time_condition = current_total_minutes >= start_total_minutes
        
        # 检查互动间隔：距离上次提醒是否超过睡眠时长（小时转秒）
        last_time = self._last_remind_time.get(user_id, 0)
        sleep_seconds = config.scheduler.sleep_hours * 3600
        interval_condition = (time.time() - last_time) > sleep_seconds
        
        should_remind = time_condition and interval_condition
        
        self.ctx.logger.debug(
            f"[喊你睡觉]检查条件: 时间={time_condition}({now.strftime('%H:%M')}>={config.scheduler.start_time}), "
            f"间隔={interval_condition}({(time.time()-last_time)/3600:.1f}h>{config.scheduler.sleep_hours}h)"
        )
        
        return {
            "should_remind": should_remind,
            "current_time": now.strftime("%H:%M"),
            "start_time": config.scheduler.start_time,
            "time_condition": time_condition,
            "interval_condition": interval_condition,
        }

    @Tool(
        "generate_goodnight_text",
        brief_description="生成催睡晚安文本",
        detailed_description="根据配置生成催睡晚安文本。如果启用了LLM，则调用LLM生成个性化文本；否则使用默认晚安文本。"
                           "参数说明：\n- stream_id：string，必填。聊天流ID，用于获取上下文。\n- user_name：string，必填。用户名称。",
        parameters=[
            ToolParameterInfo(
                name="stream_id",
                param_type=ToolParamType.STRING,
                description="聊天流ID",
                required=True,
            ),
            ToolParameterInfo(
                name="user_name",
                param_type=ToolParamType.STRING,
                description="用户名称",
                required=True,
            ),
        ],
    )
    async def generate_goodnight_text(self, stream_id: str, user_name: str, **kwargs):
        """生成晚安文本：LLM模式或默认模式"""
        config = self.config_model
        
        if config.llm_config.enable_llm:
            # 使用LLM生成：获取最近聊天上下文
            try:
                # 获取最近4小时内的消息作为上下文（API - message.get_by_time_in_chat）
                now = time.time()
                four_hours_ago = now - 4 * 3600
                
                messages = await self.ctx.message.get_by_time_in_chat(
                    chat_id=stream_id,
                    start_time=str(four_hours_ago),
                    end_time=str(now),
                )
                
                # 构建可读上下文（API - message.build_readable）
                readable_context = ""
                if messages:
                    readable_context = await self.ctx.message.build_readable(
                        messages=messages,
                        replace_bot_name=True,
                        timestamp_mode="relative",
                    )
                
                # 调用LLM生成（API - llm.generate）
                prompt = config.llm_config.llm_text
                if readable_context:
                    prompt = f"{prompt}\n\n聊天上下文：\n{readable_context}"
                
                result = await self.ctx.llm.generate(prompt=prompt)
                
                if result.get("success"):
                    return {"text": result["response"], "source": "llm"}
                else:
                    self.ctx.logger.warning("[喊你睡觉]LLM生成失败，使用默认文本")
                    
            except Exception as e:
                self.ctx.logger.error(f"[喊你睡觉]LLM调用异常: {e}")
        
        # 默认晚安文本
        return {"text": config.default_good_night.default_good_night, "source": "default"}

    # ===== Hook处理器 =====
    
    @HookHandler(
        "chat.receive.after_process",
        name="nightmare_reminder",
        description="检测消息并催睡",
        mode=HookMode.OBSERVE,  # 观察模式，不影响消息处理（API - HookMode）
        order=HookOrder.LATE,    # 延后执行（API - HookOrder）
    )
    async def check_and_remind(self, **kwargs):
        """收到消息后检查是否需要催睡"""
        config = self.config_model
        
        # 检查插件是否启用
        if not config.plugin.enabled:
            return
        
        message = kwargs.get("message", {})
        user_info = message.get("user_info", {})
        user_id = user_info.get("user_id", "")
        user_name = user_info.get("user_nickname") or user_info.get("user_name", user_id)
        stream_id = message.get("stream_id", "")
        
        # 检查是否应该催睡（调用check_sleep_time逻辑，但直接内联以简化）
        now = datetime.datetime.now()
        current_total = now.hour * 60 + now.minute
        start_parts = config.scheduler.start_time.split(":")
        start_total = int(start_parts[0]) * 60 + int(start_parts[1])
        
        time_ok = current_total >= start_total
        
        # 检查互动间隔
        last_time = self._last_remind_time.get(user_id, 0)
        sleep_seconds = config.scheduler.sleep_hours * 3600
        interval_ok = (time.time() - last_time) > sleep_seconds
        
        # 检查目标用户（无差别模式或特定用户）
        is_target = False
        if config.jam_reminder.enable_jam_reminder:
            # 无差别模式：白名单中的用户不催睡
            if user_id not in config.jam_reminder.whitelist:
                is_target = True
        else:
            # 特定用户模式
            is_target = (user_id == config.scheduler.target_user)
        
        if time_ok and interval_ok and is_target:
            # 生成晚安文本
            goodnight_result = await self.generate_goodnight_text(
                stream_id=stream_id, 
                user_name=user_name
            )
            
            goodnight_text = goodnight_result.get("text", "睡吧")
            
            # 发送催睡消息（API - send.text）
            await self.ctx.send.text(goodnight_text, stream_id)
            
            # 更新最后提醒时间
            self._last_remind_time[user_id] = time.time()
            
            # 记录日志
            self.ctx.logger.info(
                f"[喊你睡觉]:已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
                f"用户{user_name}({user_id})，聊天内容{goodnight_text[:50]}"
            )

    # ===== 原有的事件处理器（已更新）=====
    
    @EventHandler(
        "get_user_info",
        description="获取用户信息并记录互动时间",
        event_type=EventType.ON_MESSAGE,
    )
    async def on_user_message(self, message, **kwargs):
        """获取用户信息并记录互动时间"""
        user_info = message.get("user_info", {})
        user_id = user_info.get("user_id", "unknown")
        user_name = user_info.get("user_name", user_id)
        user_nickname = user_info.get("user_nickname", user_name)
        
        # 更新互动时间
        self._last_remind_time[user_id] = time.time()
        
        self.ctx.logger.debug(f"[喊你睡觉]用户 {user_name}({user_id}) 发送了消息")
        return {"intercepted": False}

    # ===== 命令处理器 =====
    
    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        """手动触发催睡测试命令"""
        message = kwargs.get("message", {})
        user_info = message.get("user_info", {})
        user_name = user_info.get("user_nickname") or user_info.get("user_name") or user_info.get("user_id", "小伙伴")
        user_id = user_info.get("user_id", "unknown")
        
        # 生成晚安文本
        goodnight_result = await self.generate_goodnight_text(
            stream_id=stream_id,
            user_name=user_name
        )
        
        goodnight_text = goodnight_result.get("text", "睡吧")
        source = goodnight_result.get("source", "default")
        
        # 发送消息（API - send.text）
        await self.ctx.send.text(goodnight_text, stream_id)
        
        # 更新提醒时间
        self._last_remind_time[user_id] = time.time()
        now = datetime.datetime.now()
        
        # 记录日志
        self.ctx.logger.info(
            f"[喊你睡觉]:已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"用户{user_name}，聊天内容{goodnight_text[:50]}，来源{source}"
        )
        
        return True, f"已向{user_name}发送催睡测试（来源：{source}）", True

    @Command("night", description="测试命令", pattern=r"^/night$")
    async def handle_nightmare(self, stream_id: str = "", **kwargs):
        """测试命令"""
        # 获取用户信息
        message = kwargs.get("message", {})
        user_info = message.get("user_info", {})
        user_name = user_info.get("user_name") or user_info.get("user_nickname") or user_info.get("user_id", "小伙伴")
    
        now = datetime.datetime.now()
        remind_message = f"晚安"
    
        await self.ctx.send.text(remind_message, stream_id)
    
    # 记录日志
        self.ctx.logger.info(f"[喊你睡觉]:已推送催睡，时间{now}，用户{user_name}，聊天内容{remind_message}")
    
        return True, f"已向{user_name}发送催睡测试", True

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        """回响"""
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1

def create_plugin():
    return NightmarePlugin()

############构建过程参见NOREADME.md############