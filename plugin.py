# ============================================================================
# 插件主体
# ============================================================================
class NightmarePlugin(MaiBotPlugin):
    async def on_load(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已加载")
        self._last_interaction: Dict[str, float] = {}
        self._last_remind: Dict[str, float] = {}
        self._load_state()

    async def on_unload(self) -> None:
        self.ctx.logger.info("[喊你睡觉]插件已卸载")
        self._save_state()

    async def on_config_update(self, scope: str, config_data: dict, version: str) -> None:
        if scope == "self":
            self.ctx.logger.info("[喊你睡觉]插件配置已更新: version=%s", version)

    config_model = NightmareConfig

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
                    or user_info.get("user_cardname")  # QQ 群名片
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
                    or sender.get("card")      # QQ 群名片
                    or sender.get("user_name")
                )
                if user_name:
                    return str(user_name)

        # 6. person API 兜底
        if user_id and platform and platform != "unknown":
            person_name = await self._get_user_name_from_person(platform, user_id)
            if person_name:
                return person_name

        # 7. 最终兜底
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

    def _should_keep_reminding(self, user_id: str) -> bool:
        """用户是否仍在活跃期（最后互动距现在 <= sleep_hours）"""
        last_interact = self._last_interaction.get(user_id, 0)
        if last_interact == 0:
            return False
        sleep_seconds = self.config.scheduler.sleep_hours * 3600
        return (time.time() - last_interact) <= sleep_seconds

    def _can_remind_now(self, user_id: str) -> bool:
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
        """执行催睡，包含 LLM 调用与日志（try18: 日志包含模型名）"""
        config = self.config
        goodnight_text = config.default_good_night.default_good_night
        llm_model_used = "default"

        if config.llm_config.enable_llm:
            try:
                available_models = []
                try:
                    available_models = await self.ctx.llm.get_available_models()
                except Exception as e:
                    self.ctx.logger.debug(f"[喊你睡觉] 无法获取可用模型列表: {e}")

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

                chosen_model = config.llm_config.llm_model.strip() if config.llm_config.llm_model else ""
                if chosen_model and available_models and chosen_model not in available_models:
                    self.ctx.logger.info(
                        f"[喊你睡觉] 指定模型 '{chosen_model}' 不可用（当前可用: {available_models}），将使用任务默认模型"
                    )
                    chosen_model = ""

                generate_kwargs = {"prompt": prompt}
                if chosen_model:
                    generate_kwargs["model"] = chosen_model

                result = await self.ctx.llm.generate(**generate_kwargs)
                if result.get("success") and result.get("response"):
                    goodnight_text = result["response"].strip()
                    llm_model_used = result.get("model") or result.get("model_name") or chosen_model or "llm"
                    self.ctx.logger.info(f"[喊你睡觉] LLM 生成成功，模型={llm_model_used}")
                else:
                    self.ctx.logger.warning("[喊你睡觉] LLM 生成失败，将使用默认文本")
            except Exception as e:
                self.ctx.logger.warning(f"[喊你睡觉] LLM 调用异常，使用默认文本: {e}")

        if not goodnight_text or not goodnight_text.strip():
            goodnight_text = "睡吧"

        await self.ctx.send.text(goodnight_text, stream_id)
        self._last_remind[user_id] = time.time()
        self._save_state()

        now = datetime.datetime.now()
        source = "llm" if llm_model_used != "default" else "default"
        self.ctx.logger.info(
            f"[喊你睡觉]:已推送催睡，时间{now.strftime('%Y-%m-%d %H:%M:%S')}，"
            f"平台{platform}，用户{user_name}({user_id})，"
            f"模型={llm_model_used}，来源={source}，"
            f"聊天内容{goodnight_text[:50]}"
        )

    # ===== Hook：每条消息触发 =====

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

        if not self._should_keep_reminding(user_id):
            self.ctx.logger.debug(f"[喊你睡觉] 用户 {user_id} 已沉默超过睡眠时长，不再催睡")
            return

        if not self._can_remind_now(user_id):
            return

        if not self._roll_probability():
            self.ctx.logger.info(f"[喊你睡觉] 概率判定未通过，跳过催睡。概率={self.config.reminder.remind_probability}")
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

    # ===== 命令处理器 =====

    @Command("nightmare", description="手动触发催睡测试", pattern=r"^/nightmare$")
    async def handle_nightmare_test(self, stream_id: str = "", **kwargs):
        # try18 - nightmare test command (静默忽略非 WebUI，日志含模型名)
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
        # try18 - night test command (静默忽略非 WebUI)
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
            f"[喊你睡觉]:已推送催睡，时间{now}，"
            f"平台{platform}，用户{user_name}，模型=N/A，来源=command，"
            f"聊天内容{remind_message}"
        )
        return True, "", True

    @Command("echo echo", pattern=r"^/echo\secho\s+(?P<text>.+)$")
    async def handle_echo(self, **kwargs):
        matched = kwargs.get("matched_groups", {})
        text = matched.get("text", "").strip()
        stream_id = kwargs["stream_id"]
        await self.ctx.send.text(text, stream_id)
        return True, text, 1


def create_plugin():
    return NightmarePlugin()

# try18 - nightmare plugin