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
# 多语言化（保持不变）
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
# WebUI插件控件生成（与之前相同，省略 NightmarePluginSection, SchedulerConfig, ReminderConfig, DefualtGoodNightConfig, JamReminderConfig, NightmareConfig）
# ... 以下仅列出 LLMConfig 变更部分，其余类保持不变 ...

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

# ... 其余配置类（NightmarePluginSection, SchedulerConfig, ReminderConfig, DefualtGoodNightConfig, JamReminderConfig, NightmareConfig）保持不变，此处省略 ...

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
        # 从 request 中提取消息列表，若没有则从 plugin 的默认提示词构建
        messages = request.get("message_list")
        if not messages:
            # 若无 message_list，视为调用错误
            raise ValueError("message_list is required")
        payload = {
            "model": config.model_name,
            "messages": messages,
            "temperature": config.temperature,
        }
        # 重用插件中的 http session
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
        self.provider = NightmareLLMProvider(self)  # 初始化自定义 Provider
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

    # 注册 LLM Provider，供主程序或其他插件使用
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

    # ===== 辅助方法（_enabled, _get_user_id, _get_platform, _get_user_name_from_person, _get_user_name 等保持不变，此处省略） =====
    # ...

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
        interval = self.config.reminder.interval_seconds
        return (time.time() - last_remind) >= interval

    def _roll_probability(self) -> bool:
        prob = self.config.reminder.remind_probability
        if prob >= 1.0:
            return True
        if prob <= 0.0:
            return False
        return random.random() < prob

    # ===== 催睡执行 =====
    async def _do_remind(self, stream_id: str, user_name: str, platform: str, user_id: str) -> None:
        config = self.config
        goodnight_text = config.default_good_night.default_good_night
        llm_model_used = "default"

        if config.llm_config.enable_llm:
            try:
                # 获取聊天上下文
                messages = await self.ctx.message.get_recent(chat_id=stream_id, limit=10)
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

                # 通过自己的 Provider 生成回复
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

    # ===== Hook、EventHandler、Commands 保持不变（含 /llmtest，但需修改其调用方式为 provider） =====
    # 注意 /llmtest 也应该使用 provider 测试
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
            resp = await self.provider.get_response(test_request)
            result = resp.get("content", "")
            self.ctx.logger.info(f"[喊你睡觉] LLM 提供商测试成功，返回: {result}")
            await self.ctx.send.text(f"✅ LLM 提供商测试成功，回复: {result}", stream_id)
            return True, "测试成功", 1
        except Exception as e:
            self.ctx.logger.error(f"[喊你睡觉] LLM 提供商测试失败: {e}")
            await self.ctx.send.text(f"❌ LLM 提供商测试失败: {e}", stream_id)
            return True, f"测试失败: {e}", 0

    # 其他命令（/nightmare, /night, /echo echo）与 try19 相同，但应将内部 LLM 调用改为 provider，已在 _do_remind 中统一，无需再改。
    # 为节省篇幅，此处省略重复的命令代码，实际部署时需保留完整。

    # ===== Hook: 每条消息触发 =====
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
        user_id = self._get_user_id(message)
        if not user_id:
            self.ctx.logger.info(f"[喊你睡觉] 未能提取 user_id，message keys: {list(message.keys())}")
            return
        self._last_interaction[user_id] = time.time()
        self._save_state()
        now = datetime.datetime.now()
        if not self._is_inside_remind_window(now):
            return
        if not self._is_target_user(user_id):
            return
        if not self._is_user_active(user_id):
            self.ctx.logger.debug(f"[喊你睡觉] 用户 {user_id} 已沉默超过睡眠时长，不再催睡")
            return
        if not self._min_remind_interval_passed(user_id):
            return
        if not self._roll_probability():
            self.ctx.logger.info(f"[喊你睡觉] 概率判定未通过，跳过催睡。概率={self.config.reminder.remind_probability}")
            return
        platform = self._get_platform(message)
        user_name = await self._get_user_name(message, user_id, platform)
        stream_id = message.get("stream_id", "")
        await self._do_remind(stream_id, user_name, platform, user_id)

    # 其他辅助方法（_get_user_id, _get_user_name 等）省略，实际代码需完整包含

def create_plugin():
    return NightmarePlugin()

# try20

######构建过程请参考NOREADME.md######