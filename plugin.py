"""
喊你睡觉：一个简单的催睡插件，过点让麦麦变成魔鬼追着你催你睡觉

2026-5-22 建立项目,将WebUI配置中文本地化，测试/night命令
2026-5-23 建立仓库，first push，

"""

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command
from typing import Dict, Optional, ClassVar
import asyncio
import random
import time, datetime

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
    """催睡时间范围设置。"""

    __ui_label__: ClassVar[str] = "催睡时间"
    __ui_order__: ClassVar[int] = 1

    start_hour: int = Field(
        default=22,
        ge=0,
        le=23,
        description="催睡开始小时（0-23）",
        json_schema_extra={
            "label": "开始时间（时）",
            "i18n": _schema_i18n(
                label_en="Start hour",
                label_ja="開始時間（時）",
                hint_en="The hour when bedtime reminders begin.",
                hint_ja="就寝リマインダーを開始する時間。",
            ),
            "order": 0,
        },
    )

    start_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="催睡开始分钟（0-59）",
        json_schema_extra={
            "label": "开始时间（分）",
            "i18n": _schema_i18n(
                label_en="Start minute",
                label_ja="開始時間（分）",
                hint_en="The minute when bedtime reminders begin.",
                hint_ja="就寝リマインダーを開始する分。",
            ),
            "order": 1,
        },
    )

    end_hour: int = Field(
        default=2,
        ge=0,
        le=23,
        description="催睡结束小时（0-23），允许跨天，例如凌晨2点",
        json_schema_extra={
            "label": "结束时间（时）",
            "i18n": _schema_i18n(
                label_en="End hour",
                label_ja="終了時間（時）",
                hint_en="The hour when bedtime reminders stop. Can cross midnight (e.g., 2 for 2 AM).",
                hint_ja="就寝リマインダーを終了する時間。日をまたぐことも可能（例：午前2時なら2）。",
            ),
            "order": 2,
        },
    )

    end_minute: int = Field(
        default=0,
        ge=0,
        le=59,
        description="催睡结束分钟（0-59）",
        json_schema_extra={
            "label": "结束时间（分）",
            "i18n": _schema_i18n(
                label_en="End minute",
                label_ja="終了時間（分）",
                hint_en="The minute when bedtime reminders stop.",
                hint_ja="就寝リマインダーを終了する分。",
            ),
            "order": 3,
        },
    )

    # 辅助属性：判断当前时间是否在催睡范围内（含跨天）
    @property
    def total_start_minutes(self) -> int:
        return self.start_hour * 60 + self.start_minute

    @property
    def total_end_minutes(self) -> int:
        return self.end_hour * 60 + self.end_minute

    def is_in_range(self, hour: int, minute: int) -> bool:
        """检查给定时间是否在催睡时间范围内（支持跨天）。"""
        current = hour * 60 + minute
        start = self.total_start_minutes
        end = self.total_end_minutes

        if start <= end:
            # 同一天内，例如 22:00 ~ 次日 02:00 的跨天情况不会走这里
            return start <= current <= end
        else:
            # 跨天，例如 22:00 ~ 02:00
            return current >= start or current <= end
        
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

class LLMusingConfig(PluginConfigBase):
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
    llm_config: LLMusingConfig = Field(default_factory=LLMusingConfig)
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

    config_model = NightmareConfig #你必须先加载webui配置

    
    @Command("night", description="测试命令", pattern=r"^/night$")
    async def handle_nightmare(self, stream_id: str = "", **kwargs):
        """测试命令"""
        del kwargs

        await self.ctx.send.text(f"👻 ", stream_id)
        return True, "测试命令", True
    
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