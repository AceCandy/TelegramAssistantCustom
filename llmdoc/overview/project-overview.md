# Project Overview

## What Is This?

TelegramAssistantCustom is a Telegram bot that automates media downloads and message management. Built with Python and Telethon.

## Core Features

1. **Media Download** - Downloads from Telegram messages (video, audio, photos)
2. **YouTube Download** - Uses yt-dlp for video/playlist downloads
3. **Bilibili Download** - Downloads B站 videos
4. **Douyin Download** - Downloads 抖音 videos
5. **Message Transfer** - Forwards messages between channels with keyword filtering
6. **Scheduled Messages** - Sends messages at configured times
7. **HDHive Integration** - Custom resolver for HDHive links
8. **Web Config Manager** - Modern web interface for managing all configuration settings

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.12+ |
| Telegram API | Telethon |
| Video Download | yt-dlp |
| Scheduler | APScheduler |
| Web Framework | FastAPI & Uvicorn |
| Config | YAML (managed via Web UI or manual editing) |
| Deployment | Docker |

## Directory Structure

```
├── main.py              # Entry point with CLI arguments
├── src/
│   ├── config/          # Configuration loading
│   ├── web/             # Web server and Config API
│   ├── handlers/        # Event handlers per platform
│   ├── services/        # Client and scheduler services
│   ├── utils/           # File utilities
│   └── constants.py     # Path constants
├── web/                 # Web UI assets (HTML, CSS, JS)
├── build.sh             # Docker build script
├── config/              # Runtime config (config.yaml)
└── downloads/           # Downloaded media storage
    ├── telegram/        # videos/, audios/, photos/, others/
    ├── youtube/
    ├── bilibili/
    └── douyin/
```

## Execution Flow

1. `main.py` loads config via `config_loader.py`
2. `ClientService` starts bot/user Telegram clients
3. `EventHandler` registers message handlers on clients
4. `SchedulerService` initializes scheduled message tasks
5. Clients run until disconnected, handling incoming messages
