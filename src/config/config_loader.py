import os
import yaml
import logging
from ..constants import CONFIG_DIR

logger = logging.getLogger(__name__)


def load_config():
    """加载配置文件"""
    config_file = os.path.join(CONFIG_DIR, "config.yaml")
    default_config = {
        "api_id": "",
        "api_hash": "",
        "api_key": "tgas",
        "user_account": {
            "enabled": False,
            "phone": "",
            "session_name": "user_session",
        },
        "bot_account": {
            "token": "",
            "id": "",
            "session_name": "bot_session",
        },
        "youtube_download": {
            "format": "bv*+ba/best",
            "cookies": "",
            "download_list": False,
        },
        "allowed_chat_ids": [],
        "scheduled_messages": [],
        "transfer_message": [],
        "log_level": "INFO",
        "proxy": {
            "enabled": False,
            "host": "127.0.0.1",
            "port": 7890,
        },
        "douyin": {
            "cookie": "",
        },
        "bilibili": {
            "cookie": "",
        },
        "send_file": False,
        "youtube_audio_convert": {
            "enabled": False,
            "format": "mp3",
        },
        "hdhive": {
            "next_action_first": "",
            "next_action_second": "",
            "next_action_unlock": "",
            "login_next_action": "",
            "server_action_login": "605db6f9f9097005c3efa316327b49963e8872c8c6",
            "server_action_encrypt": "40f37785abc6ff4ada97734df369877f373d8b1002",
            "server_action_decrypt": "40a9013be8da6c1b4846eb2bbca43f1339a4fb4f4b",
            "username": "",
            "password": "",
            "unlock_threshold": 20,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        },
    }

    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        config_updated = False

        if os.path.exists(config_file):
            with open(config_file, "r", encoding="utf-8") as file:
                config = yaml.safe_load(file) or {}
                # 合并默认配置和用户配置
                for key, value in default_config.items():
                    if key not in config:
                        config[key] = value
                        config_updated = True
                    elif isinstance(value, dict) and isinstance(config[key], dict):
                        for sub_key, sub_value in value.items():
                            if sub_key not in config[key]:
                                config[key][sub_key] = sub_value
                                config_updated = True

            # 如果有新增配置项，更新配置文件
            if config_updated:
                with open(config_file, "w", encoding="utf-8") as file:
                    yaml.dump(
                        config, file, allow_unicode=True, default_flow_style=False
                    )
                logger.info("配置文件已更新，新增配置项已添加")
        else:
            config = default_config
            with open(config_file, "w", encoding="utf-8") as file:
                yaml.dump(config, file, allow_unicode=True, default_flow_style=False)
            raise ValueError("请先配置 config/config.yaml 文件")

        # 验证必要的配置项
        if not config.get("api_id") or not config.get("api_hash"):
            raise ValueError("请在 config.yaml 中配置 api_id 和 api_hash")

        if not config.get("bot_account", {}).get("token"):
            raise ValueError("请在 config.yaml 中配置 bot_account.token")

        return config

    except Exception as e:
        logger.error(f"加载配置文件时出错: {str(e)}")
        raise
