# TelegramAssistantCustom - LLM Documentation Index

> A Telegram bot for automated media downloads from multiple platforms.

## Quick Navigation

| Document | Purpose |
|----------|---------|
| [project-overview.md](overview/project-overview.md) | What this project does, features, tech stack |
| [architecture.md](architecture/architecture.md) | Component relationships, data flow |
| [configuration.md](reference/configuration.md) | Config file structure and options |
| [handlers.md](reference/handlers.md) | Event handlers and download logic |
| [development.md](guides/development.md) | Local setup, Docker, extending the project |

## Project Summary

**TelegramAssistantCustom** is a Python Telegram bot built on Telethon that:
- Downloads media from Telegram messages (videos, audio, photos)
- Downloads videos from YouTube, Bilibili, and Douyin
- Forwards messages between channels/groups with keyword filtering
- Sends scheduled messages
- Supports both bot and user account modes

## Key Entry Points

- `main.py`: Application entry, initializes services and event loop
- `src/config/config_loader.py`: YAML configuration loading
- `src/handlers/event_handler.py`: Central event routing and handler registration
- `src/services/client_service.py`: Telegram client management
