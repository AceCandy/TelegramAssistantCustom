import re
import logging
import os
from telethon import events, errors
from .telegram_handler import TelegramHandler
from .youtube_handler import YouTubeHandler
from .douyin_handler import CustomDouyinHandler
from .bilibili_handler import BilibiliHandler
from .hdhive_handler import HDHiveResolver

logger = logging.getLogger(__name__)


class EventHandler:
    def __init__(self, config):
        self.config = config
        self.telegram_handler = TelegramHandler(config)
        self.youtube_handler = YouTubeHandler(config)
        self.douyin_handler = CustomDouyinHandler(
            config.get("douyin", {}).get("cookie")
        )
        self.bilibili_handler = BilibiliHandler(config.get("bilibili", {}))
        self.send_file = config.get("send_file", False)
        self.transfer_config = config.get("transfer_message", [])
        # 允许使用视频转发功能的chat_id列表
        self.allowed_chat_ids = config.get("allowed_chat_ids", [])
        # 缓存已获取的实体，避免重复查询
        self.entity_cache = {}

        # 创建临时目录
        self.temp_dir = os.path.join(
            os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            ),
            "temp",
        )
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)
        self.hdhive_resolver = HDHiveResolver(config)

    @staticmethod
    def _append_button_text(message_text: str, message) -> str:
        if not getattr(message, "reply_markup", None):
            return message_text

        lines = []
        for row in message.reply_markup.rows:
            for button in row.buttons:
                text = getattr(button, "text", None)
                url = getattr(button, "url", None)
                if text:
                    lines.append(text)
                if url:
                    lines.append(url)

        if not lines:
            return message_text

        separator = "\n" if message_text else ""
        return f"{message_text}{separator}{'\n'.join(lines)}"

    @staticmethod
    def _append_entity_urls(message_text: str, message) -> str:
        entities = getattr(message, "entities", None) or []
        if not entities:
            return message_text

        lines = []
        existing_urls = set(re.findall(r"https?://\S+", message_text or "", re.IGNORECASE))
        for entity in entities:
            url = getattr(entity, "url", None)
            if not isinstance(url, str):
                continue
            url = url.strip()
            if not url.startswith(("http://", "https://")):
                continue
            if url in existing_urls:
                continue
            lines.append(url)
            existing_urls.add(url)

        if not lines:
            return message_text

        separator = "\n" if message_text else ""
        return f"{message_text}{separator}{'\n'.join(lines)}"

    def is_chat_allowed(self, chat_id):
        """检查chat_id是否在允许列表中"""
        # 如果allowed_chat_ids为空列表，则允许所有
        if not self.allowed_chat_ids:
            return True
        # 检查chat_id是否在允许列表中（支持字符串和整数比较）
        return str(chat_id) in [str(allowed_id) for allowed_id in self.allowed_chat_ids]

    async def get_entity_safely(self, client, entity_id):
        """安全获取实体，处理各种可能的错误情况"""
        # 先检查缓存
        cache_key = str(entity_id)
        if cache_key in self.entity_cache:
            return self.entity_cache[cache_key]

        try:
            # 如果是整数ID或以-100开头的字符串（频道/群组ID格式）
            if isinstance(entity_id, int) or (
                isinstance(entity_id, str)
                and (entity_id.lstrip("-").isdigit() or entity_id.startswith("-100"))
            ):
                entity_id_int = int(entity_id)
                # 遍历对话列表查找匹配的ID
                async for dialog in client.iter_dialogs():
                    if dialog.id == entity_id_int:
                        logger.info(f"已找到频道/群组: {dialog.name} (ID: {dialog.id})")
                        # 缓存实体
                        self.entity_cache[cache_key] = dialog.entity
                        return dialog.entity

                # 如果遍历完所有对话后仍未找到
                logger.error(f"未找到ID为 {entity_id} 的频道/群组")
                return None
            else:
                # 对于用户名（@username格式），可以直接使用get_entity
                entity = await client.get_entity(entity_id)
                # 缓存实体
                self.entity_cache[cache_key] = entity
                return entity

        except errors.FloodWaitError as e:
            logger.error(f"请求过于频繁，需要等待 {e.seconds} 秒")
            return None
        except errors.UsernameNotOccupiedError:
            logger.error(f"用户名 {entity_id} 不存在")
            return None
        except ValueError as e:
            logger.error(f"实体获取失败: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"获取实体时发生未知错误: {str(e)}")
            return None

    async def send_video_to_user(self, event, file_path):
        """统一的发送文件方法"""
        if self.send_file:
            # 判断是视频还是音频
            is_audio = file_path.lower().endswith(
                (".mp3", ".m4a", ".ogg", ".wav", ".flac")
            )

            if is_audio:
                # 音频文件
                await event.client.send_file(
                    event.chat_id,
                    file_path,
                    force_document=False,
                    attributes=[],  # 音频属性
                )
            else:
                # 视频或其他文件
                await event.client.send_file(
                    event.chat_id,
                    file_path,
                    supports_streaming=True,
                    force_document=False,
                )

    def register_message_transfer(self, client):
        """注册消息转发处理程序（适用于用户客户端）"""
        if not self.transfer_config:
            logger.info("未配置消息转发规则，跳过注册转发处理程序")
            return

        logger.info(
            f"正在注册消息转发处理程序，共有 {len(self.transfer_config)} 条规则"
        )

        @client.on(events.NewMessage)
        async def handle_message_transfer(event):
            """处理来自任何聊天的新消息并进行转发"""
            try:
                # 获取当前聊天的ID
                chat = await event.get_chat()
                group_id = event.chat_id
                chat_username = getattr(chat, "username", None)

                # 遍历转发配置
                for transfer in self.transfer_config:
                    source_chat = transfer.get("source_chat")

                    # 检查是否匹配源聊天（通过ID或用户名）
                    source_match = False
                    if source_chat and (
                        str(group_id) == str(source_chat)
                        or (chat_username and f"@{chat_username}" == source_chat)
                    ):
                        source_match = True

                    if source_match:
                        target_chat = transfer.get("target_chat")
                        include_keywords = transfer.get("include_keywords", [])
                        exclude_words = transfer.get("exclude_words", [])
                        direct = transfer.get("direct", False)
                        # 检查是否需要根据关键词过滤
                        should_transfer = True
                        message_text = event.message.text if event.message.text else ""
                        message_text = self._append_button_text(
                            message_text, event.message
                        )
                        message_text = self._append_entity_urls(
                            message_text, event.message
                        )
                        ignore_links = transfer.get("forwardIgnoreLink", [])
                        rewritten_text = await self.hdhive_resolver.rewrite_text(
                            message_text,
                            ignore_domains=ignore_links,
                        )
                        need_modify = rewritten_text != message_text

                        # 首先检查排除词（优先级最高）
                        if exclude_words:
                            if any(
                                exclude_word in message_text
                                for exclude_word in exclude_words
                            ):
                                should_transfer = False
                                logger.info(
                                    f"消息包含排除词，跳过转发: {message_text[:50]}..."
                                )

                        # 然后检查包含词
                        if should_transfer and include_keywords:
                            # 如果指定了关键词，至少匹配一个关键词才转发
                            should_transfer = any(
                                keyword in message_text for keyword in include_keywords
                            )

                        if should_transfer:
                            try:
                                # 先获取目标频道/群组的实体
                                target_entity = await self.get_entity_safely(
                                    client, target_chat
                                )
                                if not target_entity:
                                    logger.error(
                                        f"无法获取目标频道/群组实体: {target_chat}，跳过转发"
                                    )
                                    continue

                                if direct or need_modify:
                                    logger.info(f"直接转发消息: {event.message.text}")
                                    # 检查消息是否包含photo
                                    if event.message.photo:
                                        # 如果有照片，下载到临时文件再发送
                                        temp_file_path = os.path.join(
                                            self.temp_dir,
                                            f"photo_{event.message.id}.jpg",
                                        )
                                        await event.message.download_media(
                                            temp_file_path
                                        )

                                        # 发送文本和照片
                                        await client.send_message(
                                            target_entity,
                                            (rewritten_text if need_modify else (event.message.text if event.message.text else "")),
                                            file=temp_file_path,
                                        )

                                        # 删除临时文件
                                        if os.path.exists(temp_file_path):
                                            os.remove(temp_file_path)
                                    else:
                                        # 没有照片，只发送文本
                                        await client.send_message(
                                            target_entity, (rewritten_text if need_modify else event.message.text)
                                        )
                                else:
                                    # 转发消息
                                    await client.forward_messages(
                                        target_entity, event.message
                                    )
                                    logger.info(
                                        f"已将消息从 {source_chat} 转发到 {target_chat}"
                                    )
                            except Exception as e:
                                logger.error(f"转发消息时出错: {str(e)}")

            except Exception as e:
                logger.error(f"处理消息转发时出错: {str(e)}")

    def register_handlers(self, client):
        """注册所有事件处理器"""

        @client.on(events.NewMessage(pattern="/start"))
        async def start(event):
            """处理 /start 命令"""
            await event.reply("你好！请转发视频给我，我会自动下载到指定文件夹。")

        @client.on(events.NewMessage)
        async def handle_message(event):
            """处理新消息"""
            try:
                # 先检查是否需要转发消息
                await self._handle_message_transfer(event)

                message_text = event.message.text if event.message.text else ""

                # 检查是否是YouTube链接
                youtube_pattern = r"(https?://)?(www\.)?(youtube\.com|youtu\.be)/.*|(https?://)?(m\.)?(youtube\.com|youtu\.be)/.*"
                douyin_pattern = r"https://v\.douyin\.com/.*?/"
                is_youtube = bool(re.match(youtube_pattern, message_text))
                is_douyin = bool(re.search(douyin_pattern, message_text))
                is_bilibili = (
                    "bilibili.com" in event.message.text
                    or "b23.tv" in event.message.text
                )
                if is_youtube:
                    await self._handle_youtube_message(event)
                elif is_douyin:
                    await self._handle_douyin_message(event)
                elif is_bilibili:
                    await self.handle_bilibili_message(event)
                elif event.message.media:
                    await self._handle_telegram_media(event)

            except Exception as e:
                logger.error(f"处理消息时出错: {str(e)}")
                await event.reply(f"处理消息时出错: {str(e)}")

    async def _handle_message_transfer(self, event):
        """处理消息转发（适用于机器人客户端）"""
        if not self.transfer_config:
            return

        # 获取当前聊天的ID
        chat_id = event.chat_id

        # 遍历转发配置
        for transfer in self.transfer_config:
            source_chat = transfer.get("source_chat")
            target_chat = transfer.get("target_chat")
            include_keywords = transfer.get("include_keywords", [])

            # 检查是否匹配源聊天
            if str(chat_id) == str(source_chat):
                # 检查是否需要根据关键词过滤
                should_transfer = True
                message_text = event.message.text if event.message.text else ""
                message_text = self._append_button_text(
                    message_text, event.message
                )
                message_text = self._append_entity_urls(
                    message_text, event.message
                )
                ignore_links = transfer.get("forwardIgnoreLink", [])
                rewritten_text = await self.hdhive_resolver.rewrite_text(
                    message_text,
                    ignore_domains=ignore_links,
                )
                need_modify = rewritten_text != message_text

                # 首先检查排除词（优先级最高）
                exclude_words = transfer.get("exclude_words", [])
                if exclude_words:
                    if any(
                        exclude_word in message_text for exclude_word in exclude_words
                    ):
                        should_transfer = False
                        logger.info(f"消息包含排除词，跳过转发: {message_text[:50]}...")

                # 然后检查包含词
                if should_transfer and include_keywords:
                    # 如果指定了关键词，至少匹配一个关键词才转发
                    should_transfer = any(
                        keyword in message_text for keyword in include_keywords
                    )

                if should_transfer:
                    try:
                        # 先获取目标频道/群组的实体
                        target_entity = await self.get_entity_safely(
                            event.client, target_chat
                        )
                        if not target_entity:
                            logger.error(
                                f"无法获取目标频道/群组实体: {target_chat}，跳过转发"
                            )
                            continue

                        # 检查消息是否包含photo
                        if need_modify or event.message.photo:
                            # 如果有照片，下载到临时文件再发送
                            temp_file_path = os.path.join(
                                self.temp_dir, f"photo_{event.message.id}.jpg"
                            )
                            if event.message.photo:
                                await event.message.download_media(temp_file_path)

                            # 发送文本和照片
                            await event.client.send_message(
                                target_entity,
                                (rewritten_text if need_modify else (event.message.text if event.message.text else "")),
                                file=temp_file_path if event.message.photo else None,
                            )

                            # 删除临时文件
                            if os.path.exists(temp_file_path):
                                os.remove(temp_file_path)

                            logger.info(
                                f"已将消息从 {source_chat} 发送到 {target_chat}"
                            )
                        else:
                            # 转发消息
                            await event.client.forward_messages(
                                target_entity, event.message
                            )
                            logger.info(
                                f"已将消息从 {source_chat} 转发到 {target_chat}"
                            )
                    except Exception as e:
                        logger.error(f"转发消息时出错: {str(e)}")

    async def _handle_douyin_message(self, event):
        # 检查权限
        if not self.is_chat_allowed(event.chat_id):
            logger.warning(f"未授权的chat_id尝试下载抖音视频: {event.chat_id}")
            await event.reply("❌ 抱歉，您没有权限使用此功能。")
            return

        try:
            match = re.findall(r"https?://v\.douyin\.com/.*?/", event.message.text)
            if match:
                await event.reply(f"开始下载抖音视频: {match[0]}")
                url = match[0]
                video = await self.douyin_handler.download_video(url)
                if video:
                    await event.reply(
                        f"✅ 抖音视频下载完成！\n"
                        f"标题: {video.get('desc')}\n"
                        f"保存位置: {video.get('dest_path')}"
                    )
                    # await self.send_video_to_user(event, video.get("dest_path"))
                else:
                    await event.reply("无法下载该抖音视频，请检查链接是否有效。")
            else:
                await event.reply("无法下载该抖音视频，请检查链接是否有效。")
        except Exception as e:
            await event.reply(f"下载抖音视频时出错: {str(e)}")

    async def _handle_youtube_message(self, event):
        """处理YouTube链接消息"""
        # 检查权限
        if not self.is_chat_allowed(event.chat_id):
            logger.warning(f"未授权的chat_id尝试下载YouTube视频: {event.chat_id}")
            await event.reply("❌ 抱歉，您没有权限使用此功能。")
            return

        status_message = await event.reply("开始解析YouTube下载链接...")
        try:
            success, result = await self.youtube_handler.download_video(
                event.message.text,
                lambda msg: status_message.edit(msg) if status_message else None,
            )

            if success:
                # 判断下载的文件类型
                file_type = "视频"
                if result.lower().endswith((".mp3", ".m4a", ".ogg", ".wav", ".flac")):
                    file_type = "音频"

                await event.reply(
                    f"✅ YouTube{file_type}下载完成！\n" f"保存位置: {result}"
                )
                # await self.send_video_to_user(event, result)
            else:
                await event.reply(f"❌ YouTube视频下载失败！\n" f"错误: {result}")
        except Exception as e:
            error_msg = str(e)
            if "Sign in to confirm you're not a bot" in error_msg:
                await event.reply(
                    "YouTube下载失败: 需要验证。\n"
                    "请检查配置文件中的 youtube_download.cookies 是否正确设置。"
                )
            else:
                await event.reply(f"YouTube下载失败: {error_msg}")

    async def _handle_telegram_media(self, event):
        """处理Telegram媒体消息"""
        # 检查权限
        if not self.is_chat_allowed(event.chat_id):
            logger.warning(f"未授权的chat_id尝试下载Telegram媒体: {event.chat_id}")
            await event.reply("❌ 抱歉，您没有权限使用此功能。")
            return

        status_message = await event.reply("开始下载媒体文件...")
        try:
            success, result = await self.telegram_handler.process_media(event)

            if success:
                await event.reply(
                    f"✅ {result['type']} 文件下载完成！\n"
                    f"文件名: {result['filename']}\n"
                    f"保存位置: {result['path']}"
                )
                # await self.send_video_to_user(event, result["path"])
            else:
                await event.reply(f"❌ 下载失败: {result}")
        except Exception as e:
            await event.reply(f"处理媒体文件时出错: {str(e)}")

    async def handle_bilibili_message(self, message):
        """处理消息"""
        # 检查权限
        if not self.is_chat_allowed(message.chat_id):
            logger.warning(f"未授权的chat_id尝试下载B站视频: {message.chat_id}")
            await message.reply("❌ 抱歉，您没有权限使用此功能。")
            return False

        try:
            await message.reply("正在下载B站视频，请稍候...")
            url = re.findall(
                r"https://www\.bilibili\.com/video/.*|https://b23\.tv/.*", message.text
            )
            if url:
                video = await self.bilibili_handler.download_video(url[0])
                if video:
                    await message.reply(
                        f"✅ B站视频下载完成！\n"
                        f"标题: {video.get('title')}\n"
                        f"保存位置: {video.get('path')}"
                    )
                    # await self.send_video_to_user(message, video.get("path"))
                    return True
            else:
                await message.reply("下载B站视频失败,请检查链接是否有效")
                return False

        except Exception as e:
            await message.reply(f"处理B站视频失败: {str(e)}")
            return False
