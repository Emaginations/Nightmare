这是try5，我在写一个简单的催睡插件，已经完成webui配置部分的编写，请参照开发文档帮我完成class NightmarePlugin中@Tool、@Command、@Action、@HookHandler或@EventHandler部分的编写。
请调用webui配置中设置的开始提醒的时间、LLM提示词默认设置和触发频率等设置。
请添加一个判断@Tool来检测和用户的上一次互动之间是否超过4个小时，以及是否在设置的睡眠时间之后，否侧继续触发催睡。
请添加一个@HookHandle方法或@EventHandler用self.ctx.chat获取聊天流，或尝试代码QA中新的获取方法
请添加一个@Tool方法来调用LLMConfig中的晚安提示词来生成应该提供给@HookHandle将生成的晚安文本发送给相应的聊天流Session。
请按文档添加其他需要的@Tool和@HookHandler或@EventHandler方法，尤其注意date.time get（now）获取的时间格式和设定的入睡时间点（类似22:00）格式上的不同。

请添加@Command/nightmare命令，要能触发一次测试，用上面生成的@HookHandle、@Tool等工具捕获聊天流并调用llmconfig的设置生成回复并用send.text回复，且要能看到日志显示[喊你睡觉]:已推送催睡，时间...，聊天内容...，
除此之外请不要添加多余的其他命令，也不要修改原有的两个命令。

请简要说明添加的代码及功能以及是哪个文档哪里的用法。
代码一切从简，注释除外。

*项目大纲：
# 喊你睡觉(Nightmare)

## 简介

这是一个到达设定时间点后，无论什么地方，只要你出现了麦麦就会喊你去睡觉的插件。主项目是[maibot](https://github.com/Mai-with-u/MaiBot)。

## 项目状态

⚠正在开发

## 配置

有人性化的webui设计，请在webui插件市场安装并在管理页面进行配置:

###插件开关
使能插件。

###催睡设置
在这里设定催促对象(qq号或者微信号)、开始催促的时间、睡眠时长。
####睡眠时长
设定你睡觉的时长，低于这个时间间隔发言会被继续催促，直到两次出现的间隔大于这里设定的时长。

###LLM提示词设置
在这里设置是否根据跟据上下文生成喊你睡觉的话，会消耗更多的token，但会显得更加自然。

###无差别催睡
默认关闭。开启后会无差别地催促所有人，包括你自己。
####白名单
开启无差别催睡后，白名单中的用户不会被催促。(在这个列表里的一定都是夜猫无疑。)

## 测试

在webui建立聊天,发送"/night"触发测试，
如果看到maibot日志显示[喊你睡觉]:已推送催睡，时间...，昵称...，聊天内容...，并收到晚安消息，则说明测试成功。
如果同时安装了晚安睡眠管理插件，会在插件加载时显示[喊你睡觉]:已读取晚安睡眠管理插件配置，入睡时间...。（未实现）

## 注意

请确保maibot版本为1.0.0pre24或以上,否则webui可能无法正确显示中文插件配置。

###兼容晚安睡眠管理插件，会在晚安后继续催睡。如果安装了晚安睡眠管理插件会自动读取已经设定的作息时间。

其他语言翻译没有经过仔细审核。

*已完成webui配置部分和部分Command的代码，尽量避免改动已有代码：
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

from maibot_sdk import API, Field, MaiBotPlugin, MessageGateway, PluginConfigBase, PluginContext, Tool, Command, EventHandler
from maibot_sdk.types import EventType, ToolParameterInfo, ToolParamType
from typing import Dict, Optional, ClassVar,List
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

*文档：
1.Tool 组件

@Tool 是 MaiBot 插件系统中最核心的组件类型。它允许插件向 LLM 暴露可调用的工具函数，使 LLM 能够在推理过程中主动调用外部能力——例如搜索知识库、查询数据库、调用外部 API 等。

Tool vs Action

@Action 是旧版装饰器，SDK 内部会自动将其转换为 @Tool 声明。新插件应直接使用 @Tool，不再使用 @Action。详见 Action 组件（Legacy）。
装饰器签名

from maibot_sdk import Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType

@Tool(
    name: str,                                              # 工具名称（必填）
    description: str = "",                                  # 工具描述，作为备选描述字段
    brief_description: str = "",                            # 简要描述，优先级高于 description
    detailed_description: str = "",                         # 详细描述，可包含参数说明等
    parameters: list[ToolParameterInfo] | dict | None = None,  # 参数定义
    **metadata,                                             # 额外元数据
)

参数说明
参数	类型	说明
name	str	工具名称，需在插件内唯一。LLM 通过此名称调用工具
description	str	工具备选描述。当 brief_description 为空时使用此字段
brief_description	str	工具主描述（优先使用）。传给 LLM 的工具描述摘要，帮助 LLM 判断是否需要调用
detailed_description	str	详细描述，可包含参数使用说明、注意事项等。SDK 会自动合并参数 Schema 生成完整描述
parameters	list | dict | None	工具参数定义，支持两种格式（见下文）

描述字段约定：

    description：关于工具的描述，包括使用方法，使用情景，注意事项。当 brief_description 为空时，description 会作为回退描述。
    brief_description：给主程序或小模型快速判断"这个工具是做什么的"的简要描述
    detailed_description：描述参数、必填项、可选项和调用约束的详细描述

参数定义
方式一：结构化参数（推荐）

使用 ToolParameterInfo 列表声明参数，SDK 会自动生成 JSON Schema：

from maibot_sdk import Tool, MaiBotPlugin
from maibot_sdk.types import ToolParameterInfo, ToolParamType

class MyPlugin(MaiBotPlugin):
    @Tool(
        "search",
        brief_description="搜索互联网获取信息",
        detailed_description="使用搜索引擎查找相关信息。参数说明：\n- query：string，必填。搜索关键词。\n- limit：integer，可选。返回结果数量上限。",
        parameters=[
            ToolParameterInfo(
                name="query",
                param_type=ToolParamType.STRING,
                description="搜索关键词",
                required=True,
            ),
            ToolParameterInfo(
                name="limit",
                param_type=ToolParamType.INTEGER,
                description="返回结果数量上限",
                required=False,
                default=5,
            ),
        ],
    )
    async def handle_search(self, query: str, limit: int = 5, **kwargs):
        results = await self._do_search(query, limit)
        return {"results": results}

方式二：dict 参数（兼容旧式声明）

直接传入 JSON Schema 风格的字典：

class MyPlugin(MaiBotPlugin):
    @Tool(
        "search",
        brief_description="搜索互联网获取信息",
        parameters={
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回结果数量上限", "default": 5},
        },
    )
    async def handle_search(self, query: str, limit: int = 5, **kwargs):
        results = await self._do_search(query, limit)
        return {"results": results}

ToolParameterInfo 字段
字段	类型	说明
name	str	参数名称
param_type	ToolParamType	参数类型枚举
description	str	参数描述
required	bool	是否必填，默认 True
enum_values	list | None	可选枚举值列表
default	Any	默认值
items_schema	dict | None	数组元素 Schema（当 param_type=ARRAY 时使用）
properties	dict | None	对象属性定义（当 param_type=OBJECT 时使用）
required_properties	list[str]	对象内部必填字段
additional_properties	bool | dict | None	是否允许额外字段
ToolParamType 枚举
枚举值	JSON Schema 类型	说明
STRING	string	字符串
INTEGER	integer	整数
NUMBER	number	数字（整数或浮点数）
FLOAT	number	浮点数（等价于 NUMBER）
BOOLEAN	boolean	布尔值
ARRAY	array	数组
OBJECT	object	对象
处理函数

Tool 处理函数是插件类上的异步方法，接收与参数名对应的具名参数和 **kwargs：

@Tool("greet", description="向用户打招呼",
      parameters=[
          ToolParameterInfo(name="stream_id", param_type=ToolParamType.STRING,
                          description="当前聊天流 ID", required=True),
      ])
async def handle_greet(self, stream_id: str, **kwargs):
    await self.ctx.send.text("你好！", stream_id)
    return {"success": True, "message": "已回复"}

返回值

Tool 处理函数的返回值会作为工具执行结果返回给 LLM。返回值可以是：

    dict：推荐，LLM 可以理解结构化数据
    str：简单文本结果
    其他可序列化的值

LLM 会根据返回值决定下一步操作（如向用户回复、调用其他工具等）。
返回图片和其他媒体

如果 Tool 需要把图片交给 Maisaka 继续观察或推理，不要把图片 base64 直接塞进 content。推荐返回 dict，将给 LLM 阅读的文字放在 content，将图片本体放在 content_items：

from base64 import b64encode


async def handle_draw(self, prompt: str, **kwargs):
    image_bytes = await self._draw_image(prompt)

    return {
        "success": True,
        "content": "图片已生成，请查看索引对应的图片内容。",
        "content_items": [
            {
                "type": "image",
                "data": b64encode(image_bytes).decode("ascii"),
                "mime_type": "image/png",
                "name": "result.png",
                "description": "根据提示词生成的图片",
            }
        ],
    }

也可以使用 data URL：

return {
    "success": True,
    "content": "图片已生成。",
    "content_items": [
        {
            "type": "image",
            "uri": f"data:image/png;base64,{b64encode(image_bytes).decode('ascii')}",
            "mime_type": "image/png",
            "name": "result.png",
        }
    ],
}

content_items 中常用字段如下：
字段	类型	说明
type / content_type	str	内容类型。图片使用 image；也支持 audio、resource_link、resource、binary
data / base64	str	媒体二进制的 base64 字符串，推荐图片直接使用这个字段
uri	str	媒体 URI。图片可使用 data:image/...;base64,...
mime_type	str	MIME 类型，例如 image/png、image/jpeg、image/webp
name	str	文件名或展示名称
description	str	对媒体内容的简短说明
metadata	dict	额外元数据

Maisaka 会把这类返回拆成两种上下文消息：第一条仍是纯文本 Tool Result，其中包含类似 tool_result:<tool_call_id>:1 的媒体索引；随后追加一条普通 user message，里面放入同一索引和真实图片组件。这样可以兼容不支持在 tool result 中直接回传图片的模型 API，同时让支持视觉输入的模型按普通图片消息观察图片。

视图逻辑

拆出来的图片在 LLM 输入和 Prompt 预览里会走普通 ImageComponent 的展示逻辑，和真实收到的图片消息基本一致。区别是它的来源会标记为 tool_result_media，消息 ID 是工具媒体索引，不会被当作真实用户发来的平台消息。
kwargs 中常见的额外参数
参数	类型	说明
stream_id	str	当前聊天流 ID，可用于 ctx.send.text() 等发送消息
message	dict	触发此工具调用的原始消息

stream_id

stream_id 是 Tool 组件中最重要的参数之一，它标识了当前对话流。使用 ctx.send.text("消息", stream_id) 可以将消息发送到对应的聊天流中。
描述生成规则

SDK 会自动为工具生成完整的描述信息，优先级如下：

    brief_description：优先使用（如果提供）
    description：降级回退（brief_description 为空时使用）
    detailed_description：如果提供了，SDK 会将其与参数 Schema 合并生成完整描述
    自动生成：如果上述字段都未提供，SDK 会使用 "工具 {name}" 作为描述

自动生成的参数说明格式为：

参数说明：
- query：string，必填。搜索关键词
- limit：integer，可选。返回结果数量上限。默认值：5

完整示例

from typing import Any

from maibot_sdk import MaiBotPlugin, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType


class SearchPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("搜索插件已加载")

    async def on_unload(self) -> None:
        pass

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @Tool(
        "search_web",
        description="搜索互联网获取信息",
        parameters=[
            ToolParameterInfo(
                name="query",
                param_type=ToolParamType.STRING,
                description="搜索关键词",
                required=True,
            ),
            ToolParameterInfo(
                name="limit",
                param_type=ToolParamType.INTEGER,
                description="返回结果数量上限",
                required=False,
                default=5,
            ),
        ],
    )
    async def search(self, query: str, limit: int = 5, **kwargs):
        """搜索互联网"""
        results = await self._do_search(query, limit)
        return {"results": results, "count": len(results)}

    @Tool(
        "get_weather",
        description="获取指定城市的天气信息",
        parameters=[
            ToolParameterInfo(
                name="city",
                param_type=ToolParamType.STRING,
                description="城市名称",
                required=True,
            ),
        ],
    )
    async def get_weather(self, city: str, **kwargs):
        """查询天气"""
        weather = await self._fetch_weather(city)
        return {"city": city, "weather": weather}

    async def _do_search(self, query: str, limit: int) -> list:
        # 实际搜索逻辑
        return []

    async def _fetch_weather(self, city: str) -> dict:
        # 实际天气查询逻辑
        return {}


def create_plugin():
    return SearchPlugin()



2.Command 组件

@Command 是基于正则匹配的命令组件。当用户发送的消息匹配到某个 Command 的正则模式时，MaiBot 会调度执行对应的 Command 处理函数。
装饰器签名

from maibot_sdk import Command

@Command(
    name: str,                    # 命令名称（必填）
    description: str = "",        # 命令描述
    pattern: str = "",            # 正则匹配模式
    aliases: list[str] | None = None,  # 命令别名列表
    **metadata,                   # 额外元数据
)

参数说明
参数	类型	说明
name	str	命令名称，需在插件内唯一
description	str	命令描述
pattern	str	正则匹配模式字符串。当用户消息匹配此模式时，触发该命令
aliases	list[str] | None	命令别名列表，提供额外的触发方式
基本用法

from maibot_sdk import MaiBotPlugin, Command


class MyPlugin(MaiBotPlugin):
    @Command("hello", pattern=r"^/hello")
    async def handle_hello(self, **kwargs):
        await self.ctx.send.text("Hello!", kwargs["stream_id"])
        return True, "Hello!", 2

带别名的命令

@Command("greet", pattern=r"^/greet", aliases=["/hi", "/hey"])
async def handle_greet(self, **kwargs):
    await self.ctx.send.text("你好！", kwargs["stream_id"])
    return True, "你好！", 2

使用 /greet、/hi 或 /hey 均可触发此命令。
带正则捕获组的命令

import re

@Command("echo", pattern=r"^/echo\s+(?P<text>.+)$")
async def handle_echo(self, **kwargs):
    matched = kwargs.get("matched_groups", {})
    text = matched.get("text", "").strip()
    stream_id = kwargs["stream_id"]
    await self.ctx.send.text(f"Echo: {text}", stream_id)
    return True, f"Echo: {text}", 1

处理函数参数

Command 处理函数接收 **kwargs，其中包含以下参数：
参数	类型	说明
stream_id	str	当前聊天流 ID，用于发送消息
matched_groups	dict	正则命名捕获组的匹配结果
raw_message	str	用户发送的原始消息文本
message	dict	完整的消息对象
返回值

Command 处理函数必须返回三元组：

return success, response, weight

字段	类型	说明
success	bool	命令是否成功执行
response	str	命令执行结果的文本描述
weight	int	命令优先级权重，数值越高优先级越高

# 命令成功执行
return True, "操作成功", 2

# 命令执行失败
return False, "参数错误", 1

正则模式编写指南
推荐模式

# 精确匹配 /hello
pattern=r"^/hello$"

# 匹配 /hello 加可选参数
pattern=r"^/hello(?P<name>.+)?$"

# 匹配 /echo 加必填参数
pattern=r"^/echo\s+(?P<text>.+)$"

# 匹配 /set 加键值对
pattern=r"^/set\s+(?P<key>\w+)\s+(?P<value>.+)$"

使用命名捕获组

推荐使用 (?P<name>...) 命名捕获组，可以通过 kwargs["matched_groups"] 按名称访问匹配结果：

@Command("ban", pattern=r"^/ban\s+(?P<user>\w+)(?:\s+(?P<reason>.+))?$")
async def handle_ban(self, **kwargs):
    matched = kwargs.get("matched_groups", {})
    user = matched.get("user", "")
    reason = matched.get("reason", "无原因")
    await self.ctx.send.text(f"已封禁 {user}，原因：{reason}", kwargs["stream_id"])
    return True, f"已封禁 {user}", 2

命令执行流程
插件Runner 子进程Host 主进程用户插件Runner 子进程Host 主进程用户发送消息正则匹配命令invoke_plugin(command)调用 Command 处理函数执行命令逻辑返回 (success, response, weight)返回结果
命令相关 Hook

命令执行前后有内置 Hook 点可供 @HookHandler 订阅：

    chat.command.before_execute：命令执行前触发，可中止或改写参数
    chat.command.after_execute：命令执行后触发，可改写返回结果

完整示例

from maibot_sdk import MaiBotPlugin, Command, Tool
from maibot_sdk.types import ToolParameterInfo, ToolParamType


class AdminPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("管理插件已加载")

    async def on_unload(self) -> None:
        pass

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @Command("status", pattern=r"^/status$")
    async def handle_status(self, **kwargs):
        """查看系统状态"""
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text("系统运行正常 ✅", stream_id)
        return True, "系统运行正常", 1

    @Command("echo", pattern=r"^/echo\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        """回显消息"""
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1

    @Command("help", pattern=r"^/help$", aliases=["/帮助"])
    async def handle_help(self, **kwargs):
        """显示帮助信息"""
        stream_id = kwargs["stream_id"]
        help_text = "可用命令：\n/status - 查看状态\n/echo <text> - 回显消息\n/help - 显示帮助"
        await self.ctx.send.text(help_text, stream_id)
        return True, "帮助信息已发送", 1


def create_plugin():
    return AdminPlugin()


3.API 参考

MaiBot 插件通过 self.ctx（PluginContext）访问 16 种能力代理。所有调用自动通过 RPC 转发到 Host 处理，SDK 会自动解包结果。

self.ctx.send       # 发送消息
self.ctx.db         # 数据库操作
self.ctx.llm        # LLM 调用
self.ctx.config     # 配置读取
self.ctx.message    # 历史消息
self.ctx.chat       # 聊天流
self.ctx.person     # 用户信息
self.ctx.emoji      # 表情包管理
self.ctx.frequency  # 发言频率
self.ctx.component  # 插件管理
self.ctx.api        # 跨插件 API
self.ctx.gateway    # 消息网关
self.ctx.tool       # 工具定义
self.ctx.render     # HTML 渲染
self.ctx.knowledge  # 知识库搜索
self.ctx.maisaka    # Maisaka 上下文与主动任务
self.ctx.logger     # 日志记录（标准 logging.Logger）

send — 消息发送

send = self.ctx.send

    await send.text(text, stream_id) — 发送文本消息
    await send.image(image_data, stream_id) — 发送图片
    await send.emoji(emoji_data, stream_id) — 发送表情
    await send.command(command, stream_id) — 发送指令消息
    await send.forward(messages, stream_id) — 发送转发消息
    await send.hybrid(segments, stream_id) — 发送图文混合消息
    await send.custom(custom_type, data, stream_id) — 发送自定义类型消息

# 发送文本
await self.ctx.send.text("你好", stream_id)

# 发送图片（base64）
import base64
with open("image.png", "rb") as f:
    data = base64.b64encode(f.read()).decode()
await self.ctx.send.image(data, stream_id)

# 图文混合
await self.ctx.send.hybrid([
    {"type": "text", "content": "看看这张图："},
    {"type": "image", "content": image_base64},
], stream_id)

说明：send.custom() 会同时携带 custom_type/data 和 message_type/content 两套字段名，用于兼容不同版本的 Host 实现。插件侧只需要继续传 custom_type 与 data。

所有 send.* 方法返回 bool，表示是否发送成功。
db — 数据库操作

db = self.ctx.db

    await db.query(model_name, query_type="get", data=None, filters=None, order_by=None, limit=None, single_result=False) — 通用数据库操作
    await db.save(model_name, data, key_field="id", key_value=None) — 插入或按字段更新
    await db.get(model_name, filters=None, limit=None, order_by=None, single_result=False) — 按条件获取记录
    await db.delete(model_name, filters) — 删除数据
    await db.count(model_name, filters) — 计数

db.count() 的返回值始终是 int。即使 Host 侧 RPC 返回的是带 count 字段的对象，SDK 也会自动解包。

注意：这里的 model_name 必须是 Host 侧 src.common.database.database_model 中存在的模型类名，例如 "ChatHistory"、"ActionRecord"。旧版 table 参数名和 db.get(key_field, key_value) 形式已经废弃。

# 查询
results = await self.ctx.db.query(
    model_name="ChatHistory",
    query_type="get",
    filters={"session_id": "session-123"},
    order_by=["-start_timestamp"],
    limit=10,
)

# 获取单条记录
record = await self.ctx.db.get(
    model_name="ActionRecord",
    filters={"action_id": "a-1"},
    single_result=True,
)

# 插入
await self.ctx.db.save(
    model_name="ActionRecord",
    data={"action_id": "a-1", "session_id": "session-123", "action_name": "reply"},
)

# 更新
updated = await self.ctx.db.query(
    model_name="ChatHistory",
    query_type="update",
    data={"summary": "updated"},
    filters={"session_id": "session-123"},
)

# 删除
await self.ctx.db.delete(
    model_name="ChatHistory",
    filters={"session_id": "session-123"},
)

# 计数
count = await self.ctx.db.count("ChatHistory", {"session_id": "session-123"})

llm — LLM 调用

llm = self.ctx.llm

    await llm.generate(prompt, model="", temperature=None, max_tokens=None) — 文本生成，prompt 支持字符串或消息列表
    await llm.generate_with_tools(prompt, tools, model="", temperature=None, max_tokens=None) — 带工具调用的生成
    await llm.embed(text=..., texts=...) — 生成文本嵌入向量
    await llm.get_available_models() — 获取可用模型列表，返回 list[str]

temperature 和 max_tokens 省略或传入 None 时，会使用模型管理页中当前模型/任务配置的值；只有显式传入具体值时才会覆盖配置。

generate 返回值：

{
    "success": True,
    "response": "生成的文本",
    "reasoning": "推理内容（如有）",
    "model": "实际使用的模型名",
    "model_name": "实际使用的模型名"
}

SDK 会始终补齐 model 字段；若 Host 仍返回旧字段名 model_name，SDK 会自动兼容。

# 简单文本生成
result = await self.ctx.llm.generate(
    prompt="请用一句话介绍 Python",
    temperature=0.5,
)
if result["success"]:
    text = result["response"]

# 用消息列表格式
result = await self.ctx.llm.generate(
    prompt=[
        {"role": "system", "content": "你是一个翻译助手"},
        {"role": "user", "content": "翻译：Hello World"},
    ],
)

# 带工具调用
result = await self.ctx.llm.generate_with_tools(
    prompt="今天天气怎么样",
    tools=[{
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "查询天气",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
            },
        },
    }],
)
tool_calls = result.get("tool_calls", [])

# 单条文本嵌入
embedding = await self.ctx.llm.embed(text="需要向量化的文本")

# 批量文本嵌入
embeddings = await self.ctx.llm.embed(
    texts=["第一段文本", "第二段文本"],
    task_name="embedding",
    max_concurrent=4,
)

# 获取可用模型列表
models = await self.ctx.llm.get_available_models()

config — 配置读取

config = self.ctx.config

    await config.get(key, default=None) — 获取配置值，key 支持点分割
    await config.get_plugin(plugin_name=None) — 获取指定插件的配置
    await config.get_all() — 获取插件全部配置

配置来源为插件目录下的 config.toml。

config.get()、config.get_plugin() 和 config.get_all() 都会直接返回配置值或配置字典，不需要手动从 RPC 结果中读取 value 字段。

# 读取单个值
api_key = await self.ctx.config.get("api_key", "")
timeout = await self.ctx.config.get("network.timeout", 30)

# 读取指定插件配置
config = await self.ctx.config.get_plugin("com.example.my-plugin")

# 读取全部配置
all_config = await self.ctx.config.get_all()

message — 历史消息

message = self.ctx.message

    await message.get_recent(chat_id, limit) — 获取最近消息
    await message.get_by_id(message_id, chat_id="", stream_id="") — 按消息 ID 查询单条消息
    await message.build_readable(messages, **kwargs) — 将消息列表格式化为可读字符串
    await message.get_by_time(start_time, end_time) — 按时间范围查询（全局）
    await message.get_by_time_in_chat(chat_id, start_time, end_time) — 按时间范围查询指定聊天
    await message.count_new(chat_id, since) — 统计新消息数（since 为 UNIX 时间戳字符串）

build_readable 支持两种调用方式：

# 方式 1：传入已查询的消息列表
msgs = await self.ctx.message.get_recent(chat_id, limit=20)
readable = await self.ctx.message.build_readable(msgs)

# 按消息 ID 查询
message_detail = await self.ctx.message.get_by_id(message_id, stream_id=chat_id)

# 方式 2：通过关键字参数传入 chat_id + 时间范围，由 Host 端查询
readable = await self.ctx.message.build_readable(
    messages=None,
    chat_id=chat_id,
    start_time=start_ts,
    end_time=end_ts,
)

可选关键字参数：replace_bot_name（默认 True）、timestamp_mode（默认 "relative"）、truncate（默认 False）。

message.get_by_time()、message.get_by_time_in_chat() 和 message.get_recent() 会直接返回消息列表；message.count_new() 直接返回数量；message.build_readable() 直接返回字符串。
chat — 聊天流

chat = self.ctx.chat

    await chat.get_all_streams(platform="qq") — 获取所有聊天流
    await chat.get_group_streams(platform="qq") — 获取所有群聊流
    await chat.get_private_streams(platform="qq") — 获取所有私聊流
    await chat.get_stream_by_group_id(group_id, platform="qq") — 按群 ID 查找聊天流
    await chat.get_stream_by_user_id(user_id, platform="qq") — 按用户 ID 查找私聊流
    await chat.open_session(platform, chat_type, **kwargs) — 打开或创建聊天流

# 获取所有群聊流
streams = await self.ctx.chat.get_group_streams()

# 获取私聊聊天流
streams = await self.ctx.chat.get_private_streams()

# 按 Group ID 获取聊天流
stream = await self.ctx.chat.get_stream_by_group_id(group_id="123456")

# 按用户 ID 获取聊天流
stream = await self.ctx.chat.get_stream_by_user_id(user_id="789012")

# 打开或创建私聊聊天流
stream = await self.ctx.chat.open_session(
    platform="qq",
    chat_type="private",
    user_id="789012",
)

# 打开或创建群聊聊天流
stream = await self.ctx.chat.open_session(
    platform="qq",
    chat_type="group",
    group_id="123456",
)

chat.open_session() 会返回 stream_id、session_id、chat_type、created 以及完整 stream 对象。在多账号或多路由部署中，建议同时传入 account_id 和 scope，避免打开到错误的聊天流。
maisaka — Maisaka 主动任务

# 请求 Maisaka 基于指定聊天流主动处理一轮对话
result = await self.ctx.maisaka.proactive.trigger(
    stream_id=stream["stream_id"],
    intent="提醒用户今晚 20:00 有日程",
    reason="calendar_reminder",
    metadata={"source": "calendar_plugin"},
)

# 向指定聊天流追加一条插件上下文消息
await self.ctx.maisaka.context.append(
    stream_id=stream["stream_id"],
    segments=[{"type": "text", "content": "用户刚刚完成了一个插件任务"}],
    visible_text="用户刚刚完成了一个插件任务",
    source_kind="plugin:calendar",
)

maisaka.proactive.trigger() 不会直接发送固定文本，也不会伪装成用户消息。它会把 intent 写入 Maisaka 内部上下文并唤醒 Planner，让 Maisaka 基于人格、记忆、当前上下文和可用工具自行决定是否回复以及如何表达。目标聊天流必须已经存在。
person — 用户信息

person = self.ctx.person

    await person.get_id(platform, user_id) — 获取 person_id
    await person.get_value(person_id, field_name) — 获取用户字段值
    await person.get_id_by_name(person_name) — 根据用户名获取 person_id

# 获取 person_id
pid = await self.ctx.person.get_id("qq", "12345")

# 获取昵称
name = await self.ctx.person.get_value(pid, "nickname") or "未知"

emoji — 表情包管理

emoji = self.ctx.emoji

    await emoji.get_random(count) — 随机获取表情包
    await emoji.get_by_description(description, limit) — 按描述搜索
    await emoji.get_count() — 获取总数
    await emoji.get_info() — 获取统计信息
    await emoji.get_emotions() — 获取情感标签列表
    await emoji.get_all() — 获取全部表情包
    await emoji.register_emoji(emoji_base64) — 注册新表情
    await emoji.delete_emoji(emoji_hash, keep_desc=None) — 删除表情；keep_desc=True 时保留描述缓存，仅移除文件和注册状态，False 时同步删除数据库记录，默认 None 由主程序按当前记录决定

frequency — 发言频率

frequency = self.ctx.frequency

    await frequency.get_current_talk_value(chat_id) — 获取当前 talk value
    await frequency.set_adjust(chat_id, value) — 设置频率调整值
    await frequency.get_adjust(chat_id) — 获取频率调整值

两个 get_* 方法都会直接返回数值；set_adjust() 返回布尔值表示是否设置成功。
component — 插件与组件管理

component = self.ctx.component

    await component.get_all_plugins() — 获取所有插件信息（含各插件注册的组件列表）
    await component.get_plugin_info(plugin_name) — 获取指定插件信息
    await component.list_loaded_plugins() — 列出已加载插件
    await component.list_registered_plugins() — 列出已注册插件
    await component.enable_component(name, component_type, scope="global", stream_id="") — 启用组件（name 支持 plugin_id.comp_name 全名或短名）
    await component.disable_component(name, component_type, scope="global", stream_id="") — 禁用组件（name 支持 plugin_id.comp_name 全名或短名）
    await component.load_plugin(plugin_name) — 加载插件（会校验插件是否存在并路由到对应 Supervisor）
    await component.unload_plugin(plugin_name) — 卸载插件
    await component.reload_plugin(plugin_name) — 重新加载插件

scope 支持 "global" 和 "stream"，stream 级别需传入 stream_id。

    注意：enable_component / disable_component 的 name 参数既可以传完整名称 "my_plugin.my_command"，也可以只传短名 "my_command"（Host 会自动按 component_type 匹配）。当使用短名且存在同名组件时，优先匹配指定 type 的组件。

    load_plugin() / reload_plugin() 返回 True 仅表示新 Runner 已完成初始化并成功切换；如果预热失败且 Host 回滚到旧 Runner，这两个接口会返回 False。

api — 跨插件 API

api = self.ctx.api

    await api.call(api_name, version="", **kwargs) — 调用其他插件公开的 API
    await api.get(api_name, version="") — 获取单个可见 API 的元信息
    await api.list(plugin_id="") — 列出当前插件可见的 API
    await api.replace_dynamic_apis(apis, offline_reason="动态 API 已下线") — 用新的动态 API 集合替换当前插件已暴露的动态 API

# 调用其他插件公开的 API
result = await self.ctx.api.call("plugin_a.sum_numbers", a=1, b=2)

# 查询可见 API
apis = await self.ctx.api.list()
info = await self.ctx.api.get("plugin_a.sum_numbers", version="1")

说明：

    api_name 支持完整名 plugin_id.api_name，也支持唯一短名。
    replace_dynamic_apis() 适合 MCP 服务器、外部能力市场等"API 集合会动态变化"的场景。
    动态 API 下线后，Host 会把它们标记为 offline，并对后续调用返回 offline_reason。

gateway — 消息网关

gateway = self.ctx.gateway

    await gateway.route_message(gateway_name, message, route_metadata=None, external_message_id="", dedupe_key="") — 通过指定消息网关把外部平台消息注入 Host
    await gateway.update_state(gateway_name, ready, platform="", account_id="", scope="", metadata=None) — 向 Host 上报消息网关运行时状态
    await gateway.receive_external_message(message, gateway_name=..., ...) — route_message() 的兼容别名
    await gateway.update_runtime_state(gateway_name=..., connected=..., ...) — update_state() 的兼容别名

await self.ctx.gateway.update_state(
    gateway_name="napcat_gateway",
    ready=True,
    platform="qq",
    account_id="10001",
    scope="primary",
    metadata={"protocol": "napcat"},
)

accepted = await self.ctx.gateway.route_message(
    gateway_name="napcat_gateway",
    message={
        "message_id": "msg-1",
        "platform": "qq",
        "message_info": {...},
        "raw_message": [],
    },
    route_metadata={"self_id": "10001", "connection_id": "primary"},
    external_message_id="external-1",
    dedupe_key="dedupe-1",
)

详见 消息网关。
tool — 工具定义

tool = self.ctx.tool

    await tool.get_definitions() — 获取 LLM 可用的工具定义列表

返回的列表中每个元素包含 name 和 definition 字段。tool.get_definitions() 会直接返回工具定义列表，不需要再从 RPC 结果里手动读取 tools 字段。
render — HTML 渲染

render = self.ctx.render

    await render.html2png(html, **kwargs) — 将 HTML 内容渲染为 PNG 图片

常用参数包括：

    selector：需要截图的目标选择器，默认是 body
    viewport：视口大小，例如 {"width": 1200, "height": 800}
    device_scale_factor：设备像素比
    full_page：是否截取整页
    omit_background：是否去掉默认背景
    wait_until / wait_for_selector / wait_for_timeout_ms：控制页面稳定时机
    allow_network：是否允许页面访问外部网络资源

card = await self.ctx.render.html2png(
    "<body><div id='card'>Hello MaiBot</div></body>",
    selector="#card",
    viewport={"width": 960, "height": 540},
    device_scale_factor=2.0,
)

await self.ctx.send.image(card["image_base64"], stream_id)

render.html2png() 会直接返回 Host 解包后的结果字典，通常包含 image_base64、mime_type、width 和 height 等字段。
knowledge — 知识库搜索

knowledge = self.ctx.knowledge

    await knowledge.search(query, limit=5) — 搜索 LPMM 知识库

content = await self.ctx.knowledge.search("Python 是什么", limit=3)
if content:
    print(content)

logger — 日志

# 方式一：通过 ctx.logger（名称自动为 plugin.<plugin_id>）
logger = self.ctx.logger
logger.info("插件已启动")
logger.error(f"请求失败: {err}", exc_info=True)

# 方式二：直接用 stdlib logging（同样会被自动传输）
import logging
logger = logging.getLogger(__name__)
logger.warning("配置缺失，使用默认值")

self.ctx.logger 是标准 logging.Logger，名称为 plugin.<plugin_id>。支持所有标准方法：debug()、info()、warning()、error()、critical()。

4.Hook 处理器

@HookHandler 是 MaiBot 插件系统中用于订阅命名 Hook 点的组件装饰器。主程序在关键执行点触发命名 Hook，所有订阅该 Hook 的插件处理器按固定规则调度执行，从而实现消息拦截、改写和观察。

WorkflowStep 已移除

SDK 2.0 中 WorkflowStep 已被 @HookHandler 取代。旧代码仍在使用 WorkflowStep 时会在运行时抛出 RuntimeError，这是一个不向后兼容的更改，必须迁移到 @HookHandler。
装饰器签名

from maibot_sdk import HookHandler
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy

@HookHandler(
    hook: str,                              # 订阅的命名 Hook 名称（必填）
    *,
    name: str = "",                         # 组件名称，留空时使用方法名
    description: str = "",                  # 组件描述
    mode: HookMode = HookMode.BLOCKING,     # 处理模式
    order: HookOrder = HookOrder.NORMAL,    # 同一模式内的顺序槽位
    timeout_ms: int = 0,                    # 处理器超时（毫秒），0 = 使用 Hook 默认值
    error_policy: ErrorPolicy = ErrorPolicy.SKIP,  # 异常处理策略
    **metadata,                             # 额外元数据
)

处理模式
BLOCKING（阻塞模式）

    串行执行，可以修改传入的 kwargs
    返回 modified_kwargs 可以更新后续处理器接收的参数
    返回 action: "abort" 可以终止整个 Hook 调用链
    适合需要拦截或改写消息的场景

OBSERVE（观察模式）

    后台并发执行，只读旁路观察
    不参与主流程控制，返回的 modified_kwargs 和 abort 请求会被忽略
    适合日志记录、数据分析等不影响主流程的场景

class HookMode(str, Enum):
    BLOCKING = "blocking"  # 同步等待，可修改数据
    OBSERVE = "observe"    # 异步观察，不可修改

顺序槽位

同一模式内的处理器按 order 排序执行：
值	说明
HookOrder.EARLY	优先执行，适合前置拦截
HookOrder.NORMAL	默认顺序
HookOrder.LATE	延后执行，适合补充处理
异常处理策略

当处理器抛出异常时，根据 error_policy 决定后续行为：
值	说明
ErrorPolicy.ABORT	异常时终止当前 Hook 调用
ErrorPolicy.SKIP	记录日志，跳过此处理器继续（默认）
ErrorPolicy.LOG	记录日志，并继续执行后续 hook
调度顺序

Hook 处理器按以下规则全局排序：

    模式优先：blocking 先于 observe
    顺序槽位：early → normal → late
    来源优先：内置插件先于第三方插件
    插件 ID：按字典序排列
    处理器名称：按字典序排列

基本用法
阻塞模式示例：拦截并修改消息

from maibot_sdk import MaiBotPlugin, HookHandler
from maibot_sdk.types import HookMode, HookOrder, ErrorPolicy


class MyPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @HookHandler(
        "chat.receive.before_process",
        name="message_filter",
        description="过滤入站消息",
        mode=HookMode.BLOCKING,
        order=HookOrder.EARLY,
        error_policy=ErrorPolicy.ABORT,
    )
    async def handle_message_filter(self, **kwargs):
        message = kwargs.get("message", {})
        # 过滤逻辑：如果消息包含敏感词，终止处理链
        raw_message = message.get("raw_message", "")
        if "违禁词" in raw_message:
            self.ctx.logger.info("消息被过滤: %s", raw_message)
            return {"action": "abort"}

        # 修改消息内容后继续
        kwargs["message"]["filtered"] = True
        return {"action": "continue", "modified_kwargs": kwargs}

观察模式示例：日志记录

from maibot_sdk import MaiBotPlugin, HookHandler
from maibot_sdk.types import HookMode, HookOrder


class LogPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("日志插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("日志插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @HookHandler(
        "chat.receive.after_process",
        name="message_logger",
        description="记录所有入站消息",
        mode=HookMode.OBSERVE,
        order=HookOrder.LATE,
    )
    async def observe_message(self, **kwargs):
        message = kwargs.get("message", {})
        self.ctx.logger.info(
            "观察到消息: user=%s, text=%s",
            message.get("user_id", "unknown"),
            message.get("raw_message", ""),
        )
        # observe 模式返回值会被忽略

阻塞模式示例：修改发送参数

from maibot_sdk import MaiBotPlugin, HookHandler
from maibot_sdk.types import HookMode, HookOrder


class SendInterceptorPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("发送拦截插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("发送拦截插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @HookHandler(
        "send_service.before_send",
        name="send_modifier",
        description="修改发送参数",
        mode=HookMode.BLOCKING,
        order=HookOrder.NORMAL,
        timeout_ms=5000,
    )
    async def modify_send_params(self, **kwargs):
        # 禁用打字效果，强制开启发送日志
        kwargs["typing"] = False
        kwargs["show_log"] = True
        return {"action": "continue", "modified_kwargs": kwargs}

内置 Hook 清单

以下为 Host 运行时中心表注册的全部 Hook 点。每个 Hook 注明是否允许 abort（中止调用链）和是否允许改参（修改后续处理器接收的 kwargs）。
聊天消息链
Hook 名称	触发时机	允许 abort	允许改参
chat.receive.before_process	入站消息执行 SessionMessage.process() 前	是	是
chat.receive.after_process	入站消息轻量预处理完成后	是	是
命令执行链
Hook 名称	触发时机	允许 abort	允许改参
chat.command.before_execute	命令匹配成功、正式执行前	是	是
chat.command.after_execute	命令执行结束后	否	是
表情包链
Hook 名称	触发时机	允许 abort	允许改参
emoji.maisaka.before_select	Maisaka 选择表情前	是	是
emoji.maisaka.after_select	Maisaka 选出表情后	是	是
emoji.register.after_build_description	表情包描述生成完成后	是	是
emoji.register.after_build_emotion	表情包情绪标签生成完成后	是	是
黑话（Jargon）链
Hook 名称	触发时机	允许 abort	允许改参
jargon.query.before_search	Maisaka 黑话查询前	是	是
jargon.query.after_search	Maisaka 黑话查询完成后	是	是
jargon.extract.before_persist	黑话条目写库前	是	是
jargon.inference.before_finalize	黑话推断结果写回前	是	是
表达方式（Expression）链
Hook 名称	触发时机	允许 abort	允许改参
expression.select.before_select	表达方式选择前	是	是
expression.select.after_selection	表达方式选择完成后	是	是
expression.learn.after_extract	表达方式学习解析候选后	是	是
expression.learn.before_upsert	表达方式写库前	是	是
发送服务链
Hook 名称	触发时机	允许 abort	允许改参
send_service.after_build_message	出站 SessionMessage 构建完成后	是	是
send_service.before_send	调用 Platform IO 发送前	是	是
send_service.after_send	发送流程完成后	否	否
Maisaka 规划器链
Hook 名称	触发时机	允许 abort	允许改参
maisaka.planner.before_request	Maisaka 规划器请求模型前	否	是
maisaka.planner.after_response	Maisaka 收到模型响应后	否	是
Maisaka 回复器链
Hook 名称	触发时机	允许 abort	允许改参
maisaka.replyer.before_request	Maisaka replyer 请求模型前；可读取或改写本次 reply_tool_args	否	是
maisaka.replyer.after_response	Maisaka replyer 收到模型响应后；可改写回复或要求重生成	否	是

reply_tool_args 会在表达方式选择链、maisaka.replyer.before_request 和 maisaka.replyer.after_response 中保持可见。它包含 reply 工具里除 msg_id、set_quote、reference_info 外的额外参数；before_request 返回的 reply_tool_args 修改会继续传递给后续 replyer hook。
在 replyer 请求前切换模型或追加提示词

maisaka.replyer.before_request 是 replyer 真正请求模型前的最后一个可改写点。阻塞模式处理器可以修改以下字段：
字段	类型	说明
task_name	str	本次 replyer 请求使用的任务名。修改后会用该任务的默认模型池和生成参数。
model_name	str	本次 replyer 请求指定的具体模型名称，必须存在于 model_config.toml 的 [[models]] 中。指定后只尝试该模型一次，不再按任务模型池轮换。
extra_prompt	str	追加到本次 replyer prompt 的额外回复要求。
reference_info	str	本次 reply 工具传入的引用信息，可以被改写。
reply_tool_args	dict	reply 工具额外参数，修改后会传给后续 replyer hook。

model_name 是具体模型名，不是 task 名；如果只想切换到另一个任务的模型池，修改 task_name 即可。如果同时设置 task_name 和 model_name，任务提供温度、token 上限、超时等生成参数，model_name 指定实际调用的模型。

常见用法是先通过 maisaka.planner.before_request 给内置 reply 工具追加参数 schema，让 planner 可以在调用 reply 工具时填入参数；随后在 maisaka.replyer.before_request 中读取 reply_tool_args 并路由模型：

from maibot_sdk import MaiBotPlugin, HookHandler
from maibot_sdk.types import HookMode


class ThinkingLevelPlugin(MaiBotPlugin):
    @HookHandler("maisaka.planner.before_request", mode=HookMode.BLOCKING)
    async def add_reply_tool_param(self, **kwargs):
        for tool in kwargs.get("tool_definitions", []):
            function = tool.get("function", {})
            if function.get("name") != "reply":
                continue

            parameters = function.setdefault("parameters", {})
            properties = parameters.setdefault("properties", {})
            properties["thinking_level"] = {
                "type": "string",
                "enum": ["normal", "deep"],
                "description": "回复时的思考强度。normal 表示常规回复，deep 表示使用更强模型并更细致分析。",
            }
        return {"action": "continue", "modified_kwargs": kwargs}

    @HookHandler("maisaka.replyer.before_request", mode=HookMode.BLOCKING)
    async def route_replyer_model(self, **kwargs):
        reply_tool_args = kwargs.get("reply_tool_args", {})
        if reply_tool_args.get("thinking_level") == "deep":
            kwargs["model_name"] = "your-deep-model-name"
            kwargs["extra_prompt"] = "请更细致地理解上下文后再回复。"

        return {"action": "continue", "modified_kwargs": kwargs}

只新增或修改 hook 名本身通常不需要改插件 SDK 运行时代码：@HookHandler 接收的是字符串 hook 名，是否可用由 Host 注册的 HookSpec 校验。只有需要 SDK 常量、类型提示、文档或示例同步时，才需要更新 SDK 侧内容。
Host 校验规则

Host 在插件注册阶段会对 @HookHandler 声明进行校验，不合法时插件直接注册失败（而非"加载成功但 Hook 不生效"的半成功状态）。校验规则如下：

    Hook 名称必须已注册：hook 参数必须是上述内置 Hook 清单中已存在的名称。传入未注册的 Hook 名称会导致注册失败。
    mode 必须符合 Hook 的能力约束：Host 会检查 mode 是否与该 Hook 点的能力兼容（例如，仅允许改参的 Hook 不能以不可改参的模式运行）。
    error_policy=ABORT 须 Hook 允许 abort：只有当该 Hook 的"允许 abort"列为"是"时，才能声明 error_policy=ErrorPolicy.ABORT。对于不允许 abort 的 Hook 声明 ABORT 策略将导致注册失败。

运行时 Host 会将这份 Hook 清单公开给 WebUI 后端路由 /plugins/runtime/hooks，便于面板或调试工具直接读取动态中心表。
表达方式选择链
Hook 名称	触发时机
expression.select.before_select	表达候选池载入后、默认选择结果生成前；可改写 candidates、max_num 或 abort 跳过本次选择
expression.select.after_selection	默认选择结果生成后；可改写 selected_expression_ids 或 selected_expressions

before_select 会收到 chat_id、session_id、chat_info、chat_history、reply_message、reply_tool_args、target_message、reply_reason、max_num、think_level、candidates。reply_tool_args 包含 reply 工具里除 msg_id、set_quote、reference_info 外的额外参数。after_selection 在此基础上额外包含 selected_expression_ids 与 selected_expressions。

@HookHandler("expression.select.after_selection", mode=HookMode.BLOCKING)
async def replace_expression_selection(self, **kwargs):
    strategy = kwargs.get("reply_tool_args", {}).get("expression_strategy")
    candidates = kwargs.get("candidates", [])
    selected_ids = [item["id"] for item in candidates[:1]]
    kwargs["selected_expression_ids"] = selected_ids
    return {"action": "continue", "modified_kwargs": kwargs}

处理器返回值

阻塞模式的处理器可以返回字典来控制后续流程：
返回字段	类型	说明
action	str	"continue" 继续调用链，"abort" 终止调用链
modified_kwargs	dict	修改后的参数，将传递给后续处理器

观察模式的处理器返回值会被忽略，不需要返回控制字典。
Hook 分发流程
Observe 处理器Blocking 处理器 2Blocking 处理器 1HookDispatcher主程序Observe 处理器Blocking 处理器 2Blocking 处理器 1HookDispatcher主程序触发 Hook(hook_name, kwargs)收集并排序所有处理器串行执行(kwargs){action: "continue", modified_kwargs: ...}串行执行(modified_kwargs){action: "continue", ...}后台并发执行(kwargs)返回最终结果
迁移指南：WorkflowStep → HookHandler
旧 API	新 API	说明
@WorkflowStep(stage="pre_process")	@HookHandler("chat.receive.before_process")	使用命名 Hook 点代替固定 stage
blocking=True	mode=HookMode.BLOCKING	参数名变更
observe=True	mode=HookMode.OBSERVE	参数名变更
priority=10	order=HookOrder.EARLY	改为三档枚举

DANGER

直接调用 WorkflowStep(...) 现在会立即抛出 RuntimeError，不存在兼容映射。必须手动将所有 @WorkflowStep 替换为 @HookHandler。

# 旧代码（SDK 1.x）— 不再可用
@WorkflowStep(stage="pre_process", blocking=True)
async def on_pre_process(self, **kwargs):
    ...

# 新代码（SDK 2.0）
@HookHandler("chat.receive.before_process", mode=HookMode.BLOCKING)
async def on_pre_process(self, **kwargs):
    ...

5.事件处理器

@EventHandler 是用于订阅消息和工作流事件的组件装饰器。与 @HookHandler 的命名 Hook 点机制不同，@EventHandler 基于固定的 EventType 枚举值订阅事件，适合在消息处理流程的特定阶段进行拦截或观察。
装饰器签名

from maibot_sdk import EventHandler
from maibot_sdk.types import EventType

@EventHandler(
    name: str,                                      # 组件名称（必填）
    description: str = "",                          # 组件描述
    event_type: EventType = EventType.ON_MESSAGE,   # 订阅的事件类型
    intercept_message: bool = False,                # 是否阻塞消息链
    weight: int = 0,                                # 权重，越高越先执行
    **metadata,                                     # 额外元数据
)

EventType 事件类型
枚举值	说明
UNKNOWN	未知事件
ON_START	插件启动
ON_STOP	插件停止
ON_MESSAGE_PRE_PROCESS	消息预处理阶段（过滤、拦截的最佳时机）
ON_MESSAGE	消息处理阶段
ON_PLAN	规划阶段
POST_LLM	LLM 调用后（响应已生成）
AFTER_LLM	LLM 调用完成后
POST_SEND_PRE_PROCESS	发送预处理阶段
POST_SEND	消息发送后
AFTER_SEND	消息发送完成后
intercept_message 参数

intercept_message 控制 EventHandler 是否以阻塞方式参与消息处理链：
值	行为
False（默认）	异步 fire-and-forget，不影响消息主流程
True	同步阻塞，主程序等待处理器返回后才继续

设为 True 时，处理器可以拦截、修改甚至阻止消息的后续处理。
weight 权重

多个 EventHandler 订阅同一 EventType 时，weight 决定执行顺序：

    值越高越先执行
    默认值为 0
    与旧系统的 weight 语义一致

基本用法
ON_START：插件初始化

from maibot_sdk import MaiBotPlugin, EventHandler
from maibot_sdk.types import EventType


class StartupPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @EventHandler(
        "on_startup",
        description="插件启动时初始化资源",
        event_type=EventType.ON_START,
    )
    async def handle_startup(self, **kwargs):
        self.ctx.logger.info("启动事件触发，开始初始化")
        # 在这里执行启动时需要的初始化逻辑

ON_MESSAGE_PRE_PROCESS：消息过滤

from maibot_sdk import MaiBotPlugin, EventHandler
from maibot_sdk.types import EventType


class MessageFilterPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("消息过滤插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("消息过滤插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @EventHandler(
        "spam_filter",
        description="过滤垃圾消息",
        event_type=EventType.ON_MESSAGE_PRE_PROCESS,
        intercept_message=True,   # 阻塞模式，可以拦截消息
        weight=100,               # 高权重，优先执行
    )
    async def filter_spam(self, message, **kwargs):
        raw_message = message.get("raw_message", "")
        user_id = message.get("user_info", {}).get("user_id", "")

        # 检测垃圾消息
        if self._is_spam(raw_message, user_id):
            self.ctx.logger.info("拦截垃圾消息: user=%s, text=%s", user_id, raw_message)
            return {"intercepted": True, "reason": "spam"}

        # 放行消息
        return {"intercepted": False}

    def _is_spam(self, text: str, user_id: str) -> bool:
        # 简单的垃圾消息检测逻辑
        spam_keywords = ["广告", "加群", "免费"]
        return any(kw in text for kw in spam_keywords)

ON_MESSAGE：消息观察

from maibot_sdk import MaiBotPlugin, EventHandler
from maibot_sdk.types import EventType


class MessageObserverPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self._message_count = 0

    async def on_unload(self) -> None:
        self.ctx.logger.info("总消息数: %d", self._message_count)

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @EventHandler(
        "message_counter",
        description="统计消息数量",
        event_type=EventType.ON_MESSAGE,
    )
    async def count_message(self, message, **kwargs):
        self._message_count += 1
        self.ctx.logger.debug("收到第 %d 条消息", self._message_count)

AFTER_LLM：LLM 响应后处理

from maibot_sdk import MaiBotPlugin, EventHandler
from maibot_sdk.types import EventType


class LLMPostProcessor(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("LLM 后处理插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("LLM 后处理插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @EventHandler(
        "llm_response_logger",
        description="记录 LLM 响应",
        event_type=EventType.AFTER_LLM,
        weight=50,
    )
    async def log_llm_response(self, **kwargs):
        response = kwargs.get("response", "")
        self.ctx.logger.info("LLM 响应: %s", response[:200])

POST_SEND：发送后回调

from maibot_sdk import MaiBotPlugin, EventHandler
from maibot_sdk.types import EventType


class SendAuditPlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("发送审计插件已加载")

    async def on_unload(self) -> None:
        self.ctx.logger.info("发送审计插件已卸载")

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        pass

    @EventHandler(
        "send_audit",
        description="审计所有发送的消息",
        event_type=EventType.POST_SEND,
    )
    async def audit_send(self, **kwargs):
        message = kwargs.get("message", {})
        self.ctx.logger.info(
            "消息已发送: stream_id=%s",
            message.get("stream_id", "unknown"),
        )

与 HookHandler 的区别
特性	@EventHandler	@HookHandler
订阅方式	EventType 枚举值	命名 Hook 点字符串
粒度	固定事件类型，数量有限	自定义 Hook 名称，可无限扩展
拦截方式	intercept_message=True	mode=HookMode.BLOCKING
优先级	weight 数值权重	order 三档枚举 + 全局排序
异常策略	无专用参数	error_policy 控制
适用场景	消息流程的固定阶段	主程序定义的任意扩展点

一般原则：

    如果需要在消息流程的固定阶段（如收到消息、LLM 返回后）执行逻辑，使用 @EventHandler
    如果需要订阅主程序定义的特定命名 Hook 点（如 heart_fc.heart_flow_cycle_start），使用 @HookHandler


*排障：
05-27 15:45:48 [send_service] [SendService] 已通过 Platform IO 将消息发往平台 'webui' (drivers: legacy.send.webui) message=三点四十五分啦
╭────────────────────────────── MaiSaka 循环 [1] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭────────────────────────────── Timing Gate ───────────────────────────────╮ │
│ │ 本次请求token消耗：0                                                     │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ 检测到新的提及消息（消息编号=4268fee1-fac3-43e0-857e-36f3ffea260a）  │ │ │
│ │ │ ，本轮直接跳过 Timing Gate 并视作 continue。                         │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────────────── Timing Tool ───────────────────────────────╮ │
│ │ - continue [强制跳过]:                                                   │ │
│ │ 检测到新的提及消息（消息编号=4268fee1-fac3-43e0-857e-36f3ffea260a），本  │ │
│ │ 轮直接跳过 Timing Gate 并视作 continue。                                 │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2384                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867943653.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867943653.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 1 条消息|消息 1 条|tool 0 条|cache_window 512->1024 请求模─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────────── Planner Tool · reply ──────────────────────────╮ │
│ │ - reply [成功]: "混色七"已生成并向"WebUI用户"发送了回复"三点四十五分啦"  │ │
│ │ 调用ID：call_00_78IMCTlLyxD0soX9aG7m0370                                 │ │
│ │ 执行耗时：3065.61 ms                                                     │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'msg_id': '4268fee1-fac3-43e0-857e-36f3ffea260a',                │ │ │
│ │ │     'set_quote': True                                                │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭────────────────────────────── 执行指标 ──────────────────────────────╮ │ │
│ │ │ 模型：deepseek-v4-flash                                              │ │ │
│ │ │ Token：输入 391 / 输出 45 / 总计 436                                 │ │ │
│ │ │ 耗时：prompt 5.59 ms / llm 2161.23 ms / overall 2216.65 ms           │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭──────────────────────────── Reply Prompt ────────────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/replyer/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867948809.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/replyer/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867948809.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭───────────────────────────── Reply 思考 ─────────────────────────────╮ │ │
│ │ │ 我们根据当前时间回答。用户问"现在是几点老七"，当前时间15:45:45，可以 │ │ │
│ │ │ 回答"下午三点四十五"或"15:45"。简单点。                              │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭───────────────────────────── Reply 输出 ─────────────────────────────╮ │ │
│ │ │ 三点四十五分啦                                                       │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭────────────────────────────── 阶段日志 ──────────────────────────────╮ │ │
│ │ │ prompt: 5.59 ms                                                      │ │ │
│ │ │ llm: 2161.23 ms                                                      │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰─ 流程耗时：Timing Gate 0.00 s | Planner 8.91 s | 工具执行 3.34 s | visual_re─╯
05-27 15:45:49 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=2
05-27 15:45:49 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=2 历史消息数=4 开始时间=1779867949.272
05-27 15:45:50 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:45:51 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=1024, miss_tokens=1511, hit_rate=40.39%, prompt_tokens=2535
05-27 15:45:51 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=True 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [2] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2535                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867951415.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867951415.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 4 条消息|消息 3 条|tool 1 条|cache_window 512->1024 请求模─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────── Planner Tool · finish ──────────────────────────╮ │
│ │ - finish [成功]: 当前对话循环已结束本轮思考，等待新的消息到来。          │ │
│ │ 调用ID：call_00_eQL0F78D4IWZvXI3tz1Z7655                                 │ │
│ │ 执行耗时：0.42 ms                                                        │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 2.35 s | 工具执行 0.04 s | visual_refresh 0.00 s ─────╯
05-27 15:45:55 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:00 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:03 [插件Hook分发] 观察型 HookHandler 1m.nightmare.nightmare_reminder 执行失败: plugin
05-27 15:46:03 [maisaka_runtime] [WebUI用户的私聊] 检测到提及消息，下一次 Timing Gate 将直接视作 continue；消息编号=b84ffc0b-9049-450d-b686-53eaceb1471c
05-27 15:46:03 [所见] [私聊]WebUI用户:/nigthmare
05-27 15:46:03 [maisaka_runtime] [WebUI用户的私聊] 已结束本次强制 continue 状态；触发原因=提及消息 触发消息编号=b84ffc0b-9049-450d-b686-53eaceb1471c
05-27 15:46:03 [maisaka_reasoning_engine] [WebUI用户的私聊] 检测到新的提及消息（消息编号=b84ffc0b-9049-450d-b686-53eaceb1471c），本轮直接跳过 Timing Gate 并视作 continue。
05-27 15:46:03 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=1 历史消息数=5 开始时间=1779867963.456
05-27 15:46:03 [插件运行器] 插件 1m.nightmare hook_handler nightmare_reminder 执行异常: plugin exc_info=True
05-27 15:46:05 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:05 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2048, miss_tokens=541, hit_rate=79.10%, prompt_tokens=2589
05-27 15:46:05 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=True 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [3] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭────────────────────────────── Timing Gate ───────────────────────────────╮ │
│ │ 本次请求token消耗：0                                                     │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ 检测到新的提及消息（消息编号=b84ffc0b-9049-450d-b686-53eaceb1471c）  │ │ │
│ │ │ ，本轮直接跳过 Timing Gate 并视作 continue。                         │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────────────── Timing Tool ───────────────────────────────╮ │
│ │ - continue [强制跳过]:                                                   │ │
│ │ 检测到新的提及消息（消息编号=b84ffc0b-9049-450d-b686-53eaceb1471c），本  │ │
│ │ 轮直接跳过 Timing Gate 并视作 continue。                                 │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2589                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867965756.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867965756.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 5 条消息|消息 4 条|tool 1 条|cache_window 512->1024 请求模─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────── Planner Tool · query_jargon ───────────────────────╮ │
│ │ - query_jargon [成功]: {"results": [{"word": "/nigthmare", "found":      │ │
│ │ false, "matches": []}, {"word": "/nightmare", "found": false, "matches": │ │
│ │ []}]}                                                                    │ │
│ │ 调用ID：call_00_bIC3vcW2vR0czRx9OWus8847                                 │ │
│ │ 执行耗时：112.28 ms                                                      │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'words': [                                                       │ │ │
│ │ │         '/nigthmare',                                                │ │ │
│ │ │         '/nightmare'                                                 │ │ │
│ │ │     ]                                                                │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰─ 流程耗时：Timing Gate 0.00 s | Planner 2.44 s | 工具执行 0.15 s | visual_re─╯
05-27 15:46:06 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=2
05-27 15:46:06 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=2 历史消息数=7 开始时间=1779867966.065
05-27 15:46:10 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:11 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2176, miss_tokens=518, hit_rate=80.77%, prompt_tokens=2694
05-27 15:46:11 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=True 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [4] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2694                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867971745.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867971745.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 7 条消息|消息 5 条|tool 2 条|cache_window 512->1024 请求模─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────── Planner Tool · query_jargon ───────────────────────╮ │
│ │ - query_jargon [成功]: {"results": [{"word": "/nigthmare", "found":      │ │
│ │ false, "matches": []}, {"word": "/nightmare", "found": false, "matches": │ │
│ │ []}, {"word": "nightmare", "found": false, "matches": []}]}              │ │
│ │ 调用ID：call_00_vCUrBuAYoBkCMYsBvEks8257                                 │ │
│ │ 执行耗时：9.72 ms                                                        │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'words': [                                                       │ │ │
│ │ │         '/nigthmare',                                                │ │ │
│ │ │         '/nightmare',                                                │ │ │
│ │ │         'nightmare'                                                  │ │ │
│ │ │     ]                                                                │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 5.82 s | 工具执行 0.05 s | visual_refresh 0.00 s ─────╯
05-27 15:46:11 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=3
05-27 15:46:11 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=3 历史消息数=9 开始时间=1779867971.947
05-27 15:46:15 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:16 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2176, miss_tokens=643, hit_rate=77.19%, prompt_tokens=2819
05-27 15:46:16 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=False 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [5] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2819                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867976824.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779867976824.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 9 条消息|消息 6 条|tool 3 条|cache_window 512->1024 请求模─╯ │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ 看起来 "/nigthmare"                                                  │ │ │
│ │ │ 没查到对应词条，可能是拼写错误或者某个特定的梗/指令。不过现在下午三  │ │ │
│ │ │ 点多，天还亮着呢，不是做梦的时候。                                   │ │ │
│ │ │                                                                      │ │ │
│ │ │ 没什么特别需要进一步操作的，等用户解释或者继续聊天就好。             │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────── Planner Tool · finish ──────────────────────────╮ │
│ │ - finish [成功]: 当前对话循环已结束本轮思考，等待新的消息到来。          │ │
│ │ 调用ID：call_00_6imu7eRBRUD207RpZkvG5761                                 │ │
│ │ 执行耗时：0.41 ms                                                        │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 5.01 s | 工具执行 0.08 s | visual_refresh 0.00 s ─────╯
05-27 15:46:20 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:25 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:30 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:35 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:40 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:45 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:50 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:51 [插件运行器] 插件 1m.nightmare 组件 nightmare 执行异常: llm_config exc_info=True
05-27 15:46:51 [插件运行器] 插件 1m.nightmare hook_handler nightmare_reminder 执行异常: plugin exc_info=True
05-27 15:46:51 [所见] 命令执行失败: nightmare - llm_config
05-27 15:46:51 [插件Hook分发] 观察型 HookHandler 1m.nightmare.nightmare_reminder 执行失败: plugin
05-27 15:46:51 [maisaka_runtime] [WebUI用户的私聊] 检测到提及消息，下一次 Timing Gate 将直接视作 continue；消息编号=268f784c-4968-4f19-9c10-e1550bd392fb
05-27 15:46:51 [所见] [私聊]WebUI用户:/nightmare
05-27 15:46:51 [maisaka_runtime] [WebUI用户的私聊] 已结束本次强制 continue 状态；触发原因=提及消息 触发消息编号=268f784c-4968-4f19-9c10-e1550bd392fb
05-27 15:46:51 [maisaka_reasoning_engine] [WebUI用户的私聊] 检测到新的提及消息（消息编号=268f784c-4968-4f19-9c10-e1550bd392fb），本轮直接跳过 Timing Gate 并视作 continue。
05-27 15:46:51 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=1 历史消息数=9 开始时间=1779868011.790
05-27 15:46:54 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2048, miss_tokens=763, hit_rate=72.86%, prompt_tokens=2811
05-27 15:46:54 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=False 当前为空=True 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [6] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭────────────────────────────── Timing Gate ───────────────────────────────╮ │
│ │ 本次请求token消耗：0                                                     │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ 检测到新的提及消息（消息编号=268f784c-4968-4f19-9c10-e1550bd392fb）  │ │ │
│ │ │ ，本轮直接跳过 Timing Gate 并视作 continue。                         │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────────────── Timing Tool ───────────────────────────────╮ │
│ │ - continue [强制跳过]:                                                   │ │
│ │ 检测到新的提及消息（消息编号=268f784c-4968-4f19-9c10-e1550bd392fb），本  │ │
│ │ 轮直接跳过 Timing Gate 并视作 continue。                                 │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2811                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868014439.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868014439.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 9 条消息|消息 7 条|tool 2 条|cache_window 512->1024 请求模─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭─────────────────────── Planner Tool · tool_search ───────────────────────╮ │
│ │ - tool_search [成功]: 未找到匹配的 deferred                              │ │
│ │ tools，请尝试更完整的工具名、前缀或其他关键词。                          │ │
│ │ 调用ID：call_00_9v8rRJT38hKN58tdMTf55659                                 │ │
│ │ 执行耗时：0.44 ms                                                        │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'query': 'nightmare'                                             │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰─ 流程耗时：Timing Gate 0.00 s | Planner 2.80 s | 工具执行 0.03 s | visual_re─╯
05-27 15:46:54 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=2
05-27 15:46:54 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=2 历史消息数=10 开始时间=1779868014.623
05-27 15:46:55 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:46:58 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2048, miss_tokens=839, hit_rate=70.94%, prompt_tokens=2887
05-27 15:46:58 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=True 相似度=0.00
05-27 15:46:58 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=3
╭────────────────────────────── MaiSaka 循环 [7] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：2887                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868018233.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868018233.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 10 条消息|消息 8 条|tool 2 条|cache_window 512->1024 请求 ─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭─────────────────────── Planner Tool · tool_search ───────────────────────╮ │
│ │ - tool_search [成功]: 已找到 1 个 deferred                               │ │
│ │ tools，它们会在后续轮次中加入可用工具列表：                              │ │
│ │ - moegirl_lookup（本次新发现）                                           │ │
│ │ 调用ID：call_00_6fuHat8tA7nSYZc7vvME4268                                 │ │
│ │ 执行耗时：0.46 ms                                                        │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'query': 'moegirl_lookup'                                        │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 3.75 s | 工具执行 0.00 s | visual_refresh 0.00 s ─────╯
05-27 15:46:58 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=3 历史消息数=11 开始时间=1779868018.384
05-27 15:47:00 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:00 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=1024, miss_tokens=2074, hit_rate=33.05%, prompt_tokens=3098
05-27 15:47:00 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=True 相似度=0.00
╭────────────────────────────── MaiSaka 循环 [8] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：3098                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868020734.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868020734.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 11 条消息|消息 9 条|tool 2 条|cache_window 512->1024 请求 ─╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────── Planner Tool · moegirl_lookup ──────────────────────╮ │
│ │ - moegirl_lookup [成功]: 以下词条可能相关：                              │ │
│ │ 1. Into Nightmare                                                        │ │
│ │ 简介:『イントゥ・ナイトメア』（Into                                      │ │
│ │ Nightmare）是ユリイ・カノン创作，ボカコレ官方账号于2023年8月5日投稿至nic │ │
│ │ onico，ブラックチャンネル官方账号同日投稿至Yo…                           │ │
│ │ 链接:https://zh.moegirl.org.cn/Into_Nightmare                            │ │
│ │ 2. NightmaRe                                                             │ │
│ │ 简介:NightmaRe是《地狱少女》第…                                          │ │
│ │ 调用ID：call_00_EzuD7DqhzLz3cmyPQbmT9376                                 │ │
│ │ 执行耗时：1307.41 ms                                                     │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'query': 'nightmare',                                            │ │ │
│ │ │     'mode': 'candidates'                                             │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 2.49 s | 工具执行 1.33 s | visual_refresh 0.00 s ─────╯
05-27 15:47:02 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=4
05-27 15:47:02 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=4 历史消息数=12 开始时间=1779868022.222
05-27 15:47:05 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:10 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:11 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=1920, miss_tokens=1514, hit_rate=55.91%, prompt_tokens=3434
05-27 15:47:11 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过思考相似度判定: 上一轮为空=True 当前为空=False 相似度=0.00
05-27 15:47:11 [maisaka_expression_selector] 表达方式选择已跳过：本地候选不足，session_id=4c9cd333326ab903348d207b1dd9dfd7
05-27 15:47:13 [言语] Replyer KV cache usage - hit_tokens=0, miss_tokens=929, hit_rate=0.00%, prompt_tokens=929
05-27 15:47:13 [言语] Maisaka 回复器生成成功 文本='做噩梦了？' 总耗时ms=2017.01 重生成次数=0 已选表达=[]
05-27 15:47:13 [send_service] [SendService] 已通过 Platform IO 将消息发往平台 'webui' (drivers: legacy.send.webui) message=做噩梦了？
╭────────────────────────────── MaiSaka 循环 [9] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：3434                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868031104.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868031104.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 12 条消息|消息 9 条|tool 3 条|cache_window 512->1024 请求 ─╯ │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ ## 分析                                                              │ │ │
│ │ │                                                                      │ │ │
│ │ │ 用户先问了时间，混色七已经回答了（三点四十五）。然后用户连续发了三次 │ │ │
│ │ │ "/nigthmare" 和 "/nightmare"                                         │ │ │
│ │ │ ——先是拼错，然后纠正。看起来用户在尝试某种指令或梗，但查了黑话库和萌 │ │ │
│ │ │ 百都没找到直接匹配的聊天指令/功能。                                  │ │ │
│ │ │                                                                      │ │ │
│ │ │ 用户可能是：                                                         │ │ │
│ │ │ 1. 在玩某种梗或想触发某个功能，但这里没有对应的实现                  │ │ │
│ │ │ 2. 打错了字后反复尝试                                                │ │ │
│ │ │                                                                      │ │ │
│ │ │ **判断**：混色七应当注意到这个重复行为，以轻松的方式回应一下，表示"  │ │ │
│ │ │ 这个指令我不认识啊"或者玩味地接一下"nightmare"这个主题。不宜无视用户 │ │ │
│ │ │ 的多次尝试，那样会显得冷漠。                                         │ │ │
│ │ │                                                                      │ │ │
│ │ │ 可以自然地接一句，保持混色七的轻松风格。同时不用再查更多资料了，证据 │ │ │
│ │ │ 已经足够判断。                                                       │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭────────────────────────── Planner Tool · reply ──────────────────────────╮ │
│ │ - reply [成功]: "混色七"已生成并向"WebUI用户"发送了回复"做噩梦了？"      │ │
│ │ 调用ID：call_00_OfyIDK860aZx3lJdhhGk2326                                 │ │
│ │ 执行耗时：2497.49 ms                                                     │ │
│ │ ╭────────────────────────────── 工具参数 ──────────────────────────────╮ │ │
│ │ │ {                                                                    │ │ │
│ │ │     'msg_id': '268f784c-4968-4f19-9c10-e1550bd392fb'                 │ │ │
│ │ │ }                                                                    │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭────────────────────────────── 执行指标 ──────────────────────────────╮ │ │
│ │ │ 模型：deepseek-v4-flash                                              │ │ │
│ │ │ Token：输入 929 / 输出 65 / 总计 994                                 │ │ │
│ │ │ 耗时：prompt 2.29 ms / llm 2011.09 ms / overall 2017.01 ms           │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭──────────────────────────── Reply Prompt ────────────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/replyer/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868033780.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/replyer/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868033780.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭───────────────────────────── Reply 思考 ─────────────────────────────╮ │ │
│ │ │ 我们看了看用户反复尝试的打字和消息记录，用户从拼错的 "nigthmare"     │ │ │
│ │ │ 纠正到 "nightmare"。混色七定位是表情包代餐朋友，轻松幽默风格，可以用 │ │ │
│ │ │ "做噩梦了？" 来调侃这个无效指令，同时保持简洁。                      │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭───────────────────────────── Reply 输出 ─────────────────────────────╮ │ │
│ │ │ 做噩梦了？                                                           │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ │ ╭────────────────────────────── 阶段日志 ──────────────────────────────╮ │ │
│ │ │ prompt: 2.29 ms                                                      │ │ │
│ │ │ llm: 2011.09 ms                                                      │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 9.03 s | 工具执行 2.53 s | visual_refresh 0.00 s ─────╯
05-27 15:47:13 [maisaka_reasoning_engine] [WebUI用户的私聊] 跳过 Timing Gate，继续执行 Planner: 回合=5
05-27 15:47:13 [maisaka_reasoning_engine] [WebUI用户的私聊] 规划器开始执行: 回合=5 历史消息数=14 开始时间=1779868033.836
05-27 15:47:15 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:17 [maisaka_chat_loop] Maisaka KV cache usage - request_kind=planner, hit_tokens=2432, miss_tokens=1255, hit_rate=65.96%, prompt_tokens=3687
╭───────────────────────────── MaiSaka 循环 [10] ──────────────────────────────╮
│ 聊天流名称：WebUI用户的私聊                                                  │
│ 聊天流ID：4c9cd333326ab903348d207b1dd9dfd7                                   │
│ ╭──────────────────────────────── Planner ─────────────────────────────────╮ │
│ │ 请求模型：deepseek-v4-flash                                              │ │
│ │ 本次请求token消耗：3687                                                  │ │
│ │ ╭─────────────────── MaiSaka 大模型请求 - 对话单步 ────────────────────╮ │ │
│ │ │ html预览：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868037572.html 在浏览器打开 Prompt           │ │ │
│ │ │ 原始文本：logs/maisaka_prompt/planner/webui_private_webui_user_webui │ │ │
│ │ │ _0f54a64ka_mp54cuzb/1779868037572.txt 点击打开 Prompt 文本           │ │ │
│ │ ╰─ 实际发送 14 条消息|消息 11 条|tool 3 条|cache_window 512->1024 请求─╯ │ │
│ │ ╭──────────────────────────── Maisaka 返回 ────────────────────────────╮ │ │
│ │ │ ## 分析                                                              │ │ │
│ │ │                                                                      │ │ │
│ │ │ 混色七已经对用户的"/nightmare"做出了自然回应（"做噩梦了？"）——这个回 │ │ │
│ │ │ 应很合适：                                                           │ │ │
│ │ │ 1. 用轻松的方式解释了用户的指令尝试                                  │ │ │
│ │ │ 2. 给用户一个接话的台阶                                              │ │ │
│ │ │ 3. 保持了混色七随性自然的风格                                        │ │ │
│ │ │                                                                      │ │ │
│ │ │ 目前没有新的用户反馈进来，无需继续操作。等待用户后续回应即可。       │ │ │
│ │ ╰──────────────────────────────────────────────────────────────────────╯ │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
│ ╭───────────────────────── Planner Tool · finish ──────────────────────────╮ │
│ │ - finish [成功]: 当前对话循环已结束本轮思考，等待新的消息到来。          │ │
│ │ 调用ID：call_00_yw8wLQdvYse4KZAdw8AA1413                                 │ │
│ │ 执行耗时：0.38 ms                                                        │ │
│ ╰──────────────────────────────────────────────────────────────────────────╯ │
╰───── 流程耗时：Planner 3.88 s | 工具执行 0.03 s | visual_refresh 0.00 s ─────╯
05-27 15:47:20 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:25 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:30 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:35 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:40 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:45 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:50 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:47:55 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:48:00 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:48:05 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:48:10 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:48:15 [plugin.maibot-team.snowluma-adapter] SnowLuma 连接异常，稍后重试: Cannot connect to host snowluma:3001 ssl:default [Connect call failed ('172.19.0.5', 3001)]
05-27 15:48:17 [插件Hook分发] 观察型 HookHandler 1m.nightmare.nightmare_reminder 执行失败: plugin
05-27 15:48:17 [send_service] [SendService] 已通过 Platform IO 将消息发往平台 'webui' (drivers: legacy.send.webui) message=晚安
05-27 15:48:17 [插件运行器] 插件 1m.nightmare hook_handler nightmare_reminder 执行异常: plugin exc_info=True
05-27 15:48:17 [plugin.1m.nightmare] [喊你睡觉]:已推送催睡，时间2026-05-27 15:48:17.712490，用户小伙伴，聊天内容晚安
05-27 15:48:17 [所见] 命令执行成功: night (拦截等级: 1)
05-27 15:48:17 [所见] 命令处理完成，跳过后续消息处理: 已向小伙伴发送催睡测试

为什么我/nightmare 命令不起效？