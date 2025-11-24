#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from telethon import TelegramClient, errors

# 添加项目根目录到系统路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.handlers.channel_transfer_handler import ChannelTransferHandler
from src.config.config_loader import load_config

# 配置日志
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
# 获取程序所在目录的绝对路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")

# 在这里设置参数
SOURCE_CHANNEL = ""  # 源频道的用户名或ID，注意不要加引号
TARGET_CHANNEL = ""  # 目标频道的用户名或ID
SINCE_DATE = "2025-10-1 9:35:00"  # 只转发该日期之后的消息，格式：YYYY-MM-DD HH:MM:SS
RUN_ONCE = True  # 设置为True表示只执行一次转发，设置为False表示定时转发
INTERVAL_HOURS = 24  # 定时转发的间隔时间（小时），仅当RUN_ONCE=False时生效
DIRECT = True  # 是否直接转发消息


async def get_entity_safely(client, entity_id):
    """安全获取实体，处理各种可能的错误情况"""
    try:
        # 如果是整数ID，尝试直接通过对话列表查找
        if isinstance(entity_id, int) or (
            isinstance(entity_id, str) and entity_id.startswith("-100")
        ):
            entity_id = int(entity_id)
            # 遍历对话列表查找匹配的ID
            async for dialog in client.iter_dialogs():
                if dialog.id == entity_id:
                    logger.info(f"已找到频道: {dialog.name} (ID: {dialog.id})")
                    return dialog.entity

            # 如果遍历完所有对话后仍未找到
            logger.error(f"未找到ID为 {entity_id} 的频道，请确认您已加入该频道")
            return None
        else:
            # 对于用户名，可以直接使用get_entity
            entity = await client.get_entity(entity_id)
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


async def main():
    """主程序入口"""
    try:
        # 加载配置
        config = load_config()

        # 创建Telegram客户端
        api_id = config["api_id"]
        api_hash = config["api_hash"]
        session_name = config["user_account"]["session_name"]
        session_file = os.path.join(CONFIG_DIR, session_name)

        client = TelegramClient(session_file, api_id, api_hash)
        await client.start()

        if not client.is_connected():
            logger.error("客户端连接失败")
            return 1

        logger.info("客户端连接成功")

        # 安全获取源频道和目标频道实体
        source_entity = await get_entity_safely(client, SOURCE_CHANNEL)
        if not source_entity:
            logger.error("无法获取源频道实体，请检查频道ID是否正确并确保您已加入该频道")
            logger.info("提示：可以运行 list_channels.py 查看您有权限访问的所有频道")
            return 1

        target_entity = await get_entity_safely(client, TARGET_CHANNEL)
        if not target_entity:
            logger.error(
                "无法获取目标频道实体，请检查频道ID是否正确并确保您已加入该频道"
            )
            logger.info("提示：可以运行 list_channels.py 查看您有权限访问的所有频道")
            return 1

        # 创建频道转发处理器
        handler = ChannelTransferHandler(client, config)

        # 解析日期字符串
        try:
            since_date = datetime.strptime(SINCE_DATE, "%Y-%m-%d %H:%M:%S")
            # 添加UTC时区信息
            since_date = since_date.replace(tzinfo=timezone.utc)
            logger.info(f"设置起始日期为: {since_date.isoformat()}")
        except ValueError:
            logger.error("日期格式错误，请使用格式：YYYY-MM-DD HH:MM:SS")
            return 1

        # 执行转发
        if RUN_ONCE:
            logger.info(
                f"开始从 {source_entity.title} 向 {target_entity.title} 转发消息..."
            )
            count = await handler.transfer_messages(
                source_entity, target_entity, since_date, direct=DIRECT
            )
            logger.info(f"转发完成，共转发 {count} 条消息")
        else:
            logger.info(
                f"开始定时任务，每 {INTERVAL_HOURS} 小时从 {source_entity.title} 向 {target_entity.title} 转发消息..."
            )
            try:
                await handler.schedule_transfer(
                    source_entity,
                    target_entity,
                    since_date,
                    interval_hours=INTERVAL_HOURS,
                )
            except KeyboardInterrupt:
                logger.info("定时任务被用户中断")

    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        return 1

    finally:
        # 断开客户端连接
        await client.disconnect()
        logger.info("客户端已断开连接")

    return 0


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}")
        sys.exit(1)
