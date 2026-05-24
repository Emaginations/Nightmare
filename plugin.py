"""
喊你睡觉：一个简单的催睡插件

2026-5-22 建立项目,尝试将WebUI配置中文本地化
2026-5-23 调整催睡时间设置的时间格式，添加睡眠时长sleep_hours,尝试获取用户ID
2026-5-24 增补readme，进行详细功能说明(设计),添加无差别催睡功能，默认关闭
"""

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command, EventHandler
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType
from typing import Dict, Optional, ClassVar
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
    """插件开关配置。"""

    __ui_label__: ClassVar[str] = "插件设置"
    __ui_order__: ClassVar[int] = 0

    enabled: bool = Field(
        default=False,
        description="是否启用喊你睡觉插件",
        json_schema_extra={
            "label": "开关",
            "i18n": _schema_i18n(
                label_en="Enable adapter",
                label_ja="アダプターを有効化",
                hint_en="When disabled, the plugin only registers the message gateway and will not connect to SnowLuma.",
                hint_ja="無効にすると、プラグインはメッセージゲートウェイの登録のみを行い、SnowLuma へ接続しません。",
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

class SchedulerConfig(PluginConfigBase):
    """催睡时间设置。"""

    __ui_label__: ClassVar[str] = "催睡时间"
    __ui_order__: ClassVar[int] = 1

    user: str = Field(
        default="你必须先填写用户名",
        description="用户名",
        json_schema_extra={
            "label": "用户名",
            "i18n": _schema_i18n(
                label_en="User name",
                label_ja="ユーザー名"                        
            ),
            "order": 0,
        }
    )

    start_time: str = Field(
        default="22:00",
        pattern=r"^([01]\d|2[0-3]):([0-5]\d)$",
        description="催促开始时间（格式 HH:MM，例如 22:00）",
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
    
    # 睡眠时长：4-12小时，步进1小时
    sleep_hours: int = Field(
    default=8,
    ge=4,
    le=12,
    description="设定你睡觉的时长，低于这个时间间隔发言会被继续催促，默认为4小时",
    json_schema_extra={
        "label": "睡眠时长（小时）",
        "hint": "设定你睡觉的时长，低于这个时间间隔发言会被继续催促，默认为4小时",
        "x-widget": "slider",
        "min": 4,
        "max": 12,
        "step": 1,
        "i18n": _schema_i18n(
            label_en="Sleep hours",
            label_ja="睡眠時間（時間）",
            hint_en="Your sleep duration. Reminders will continue if the interval is less than this value. Default is 4 hours.",
            hint_ja="あなたの睡眠時間。この時間より間隔が短い場合、リマインダーは続行されます。デフォルトは4時間です。",
        ),
        "order": 2,
    },
)

    # 辅助方法：获取开始时间的总分钟数
    @property
    def total_start_minutes(self) -> int:
        """获取开始时间的总分钟数"""
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
        default="晚安",
        description="喊你睡觉",
        json_schema_extra={
            "label": "默认晚安",
            "hint": "说是喊你睡觉",
            "i18n": _schema_i18n(
                label_en="Default good night",
                label_ja="デフォルトの夜寝",
                hint_en="Default good night",
                hint_ja="デフォルトの夜寝",
            ),
            "order": 0,
        },
    )

class NightmareConfig(PluginConfigBase):
    """配置大纲"""
    plugin: NightmarePluginSection = Field(default_factory=NightmarePluginSection)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    reminder: ReminderConfig = Field(default_factory=ReminderConfig)
    llm_config: LLMConfig = Field(default_factory=LLMConfig)
    default_good_night: DefualtGoodNightConfig = Field(default_factory=DefualtGoodNightConfig)



# ============================================================================
# 插件主体
# ============================================================================
class NightmarePlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig #你必须先加载配置

    @EventHandler(
    "get_user_info",
    description="获取用户信息",
    event_type=EventType.ON_MESSAGE,
)
    async def on_user_message(self, message, **kwargs):
        """获取用户信息示例"""
        user_info = message.get("user_info", {})
        user_id = user_info.get("user_id", "unknown")
        user_name = user_info.get("user_name", user_id)
        user_nickname = user_info.get("user_nickname", user_name)
    
        # 更新互动时间时使用用户ID
        self._last_remind_time[user_id] = time.time()
    
        self.ctx.logger.info(f"[喊你睡觉]用户 {user_name}({user_id}) 发送了消息")
        return {"intercepted": False}


    @Command("night", description="测试命令", pattern=r"^/night$")
    async def handle_nightmare(self, stream_id: str = "", **kwargs):
        """测试命令"""
        # 获取用户信息
        message = kwargs.get("message", {})
        user_info = message.get("user_info", {})
        user_name = user_info.get("user_name") or user_info.get("user_nickname") or user_info.get("user_id", "小伙伴")
    
        now = datetime.datetime.now()
        remind_message = f"💤 {user_name}，现在时间 {now.strftime('%H:%M')}，该睡觉啦！💤"
    
        await self.ctx.send.text(remind_message, stream_id)
    
    # 记录日志
        self.ctx.logger.info(f"[喊你睡觉]:已推送催睡，时间{now}，用户{user_name}，聊天内容{remind_message}")
    
        return True, f"已向{user_name}发送催睡测试", True

    @Command("echo", pattern=r"^/echo\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        """回响"""
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1

def create_plugin():
    return NightmarePlugin()