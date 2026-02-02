import os
import logging
import asyncio
import signal
import argparse
from logging.handlers import TimedRotatingFileHandler

logger = logging.getLogger(__name__)

# Config directory for logging (used before full config load)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(BASE_DIR, "config")


def configure_logging(log_level: str = "INFO") -> None:
    log_dir = os.path.join(CONFIG_DIR, "log")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "app.log")

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler = TimedRotatingFileHandler(
        log_file, when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(description="TelegramAssistant Bot")
    parser.add_argument(
        "--web",
        action="store_true",
        help="启动 Web 配置管理界面",
    )
    parser.add_argument(
        "--web-only",
        action="store_true",
        help="仅启动 Web 服务器（不启动 Telegram Bot）",
    )
    parser.add_argument(
        "--web-port",
        type=int,
        default=12321,
        help="Web 服务器端口（默认: 12321",
    )
    parser.add_argument(
        "--web-host",
        type=str,
        default="127.0.0.1",
        help="Web 服务器地址（默认: 127.0.0.1）",
    )
    return parser.parse_args()


async def run_bot():
    """运行 Telegram Bot"""
    # Lazy imports to avoid loading broken modules when using --web-only
    from src.config.config_loader import load_config
    from src.services.client_service import ClientService
    from src.services.scheduler_service import SchedulerService
    from src.handlers.event_handler import EventHandler
    from src.utils.file_utils import ensure_dirs
    from src.constants import (
        TELEGRAM_TEMP_DIR,
        YOUTUBE_TEMP_DIR,
        TELEGRAM_VIDEOS_DIR,
        TELEGRAM_AUDIOS_DIR,
        TELEGRAM_PHOTOS_DIR,
        TELEGRAM_OTHERS_DIR,
        YOUTUBE_DEST_DIR,
    )

    try:
        # 加载配置
        config = load_config()

        # 创建所有必要的目录
        ensure_dirs(
            TELEGRAM_TEMP_DIR,
            YOUTUBE_TEMP_DIR,
            TELEGRAM_VIDEOS_DIR,
            TELEGRAM_AUDIOS_DIR,
            TELEGRAM_PHOTOS_DIR,
            TELEGRAM_OTHERS_DIR,
            YOUTUBE_DEST_DIR,
        )

        # 设置日志级别
        logging.getLogger().setLevel(config.get("log_level", "INFO"))

        # 初始化服务
        client_service = ClientService(config)
        scheduler_service = SchedulerService()
        event_handler = EventHandler(config)

        # 启动客户端
        user_client = await client_service.start_user_client()
        bot_client = await client_service.start_bot_client()

        if not (user_client or bot_client):
            raise ValueError("未启用任何客户端，请在配置文件中至少启用一个客户端")

        # 注册事件处理器
        if bot_client:
            event_handler.register_handlers(bot_client)

        # 初始化定时任务和消息转发功能
        if user_client:
            # 注册消息转发处理程序（在用户客户端上）
            event_handler.register_message_transfer(user_client)

            # 初始化定时任务
            scheduler_service.initialize_tasks(
                user_client, config.get("scheduled_messages", [])
            )
            scheduler_service.start()

        # 设置关闭处理
        loop = asyncio.get_event_loop()

        async def shutdown(signal_=None):
            """优雅关闭"""
            if signal_:
                logger.info(f"收到信号 {signal_.name}...")

            # 取消所有任务
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            [task.cancel() for task in tasks]
            logger.info(f"取消 {len(tasks)} 个待处理的任务")
            await asyncio.gather(*tasks, return_exceptions=True)

            # 关闭客户端
            await client_service.disconnect_all()

            # 关闭调度器
            scheduler_service.shutdown()

            loop.stop()

        # 注册信号处理器
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s)))

        # 运行客户端
        await asyncio.gather(
            *(client.run_until_disconnected() for client in client_service.clients)
        )

    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}")
        raise


async def main():
    """主程序入口"""
    args = parse_args()
    configure_logging("INFO")

    if args.web_only:
        # 仅启动 Web 服务器
        from src.web.web_server import run_server
        logger.info(f"启动 Web 配置管理界面: http://{args.web_host}:{args.web_port}")
        await run_server(host=args.web_host, port=args.web_port)
    elif args.web:
        # 同时启动 Bot 和 Web 服务器
        from src.web.web_server import run_server
        logger.info(f"启动 Web 配置管理界面: http://{args.web_host}:{args.web_port}")
        await asyncio.gather(
            run_bot(),
            run_server(host=args.web_host, port=args.web_port),
        )
    else:
        # 仅启动 Bot
        await run_bot()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序异常退出: {str(e)}")
