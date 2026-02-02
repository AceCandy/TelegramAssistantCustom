# Development Guide

## Local Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Create `config/config.yaml` with API credentials
4. Run initialization: `python init.py` (for first-time setup)
5. Start with options:
   - `python main.py` (Bot only)
   - `python main.py --web` (Bot + Web Config)
   - `python main.py --web-only` (Web Config only)
   - `python main.py --web-port 12321` (Custom Port)

## Docker Setup

### Building the image

Use the provided build script to package the application:
```bash
chmod +x build.sh
./build.sh
```

### Running with Docker Compose

```bash
docker-compose up -d
```
The Web UI will be available at `http://host-ip:12321`.

### Commands

```bash
docker exec -it telegram_assistant python /app/init.py
docker restart telegram_assistant
```

## Adding a New Download Handler

1. Create `src/handlers/{platform}_handler.py`
2. Implement download logic with temp/dest file paths
3. Add handler instance to `EventHandler.__init__`
4. Add URL pattern detection in `EventHandler.handle_message`
5. Add constants in `src/constants.py` for directories

## Adding a New Configuration Option

1. Add default value in `src/config/config_loader.py:default_config`
2. Access via `self.config.get("key")` in handlers
3. Document in `config/config.yaml` example

## File Path Constants

All paths defined in `src/constants.py`:
- `BASE_DIR` - Project root
- `CONFIG_DIR` - `config/`
- `TEMP_DIR` - `temp/`
- `*_DEST_DIR` - Final download destinations

## Logging

Configured in `main.py:configure_logging()`:
- File: `config/log/app.log` (daily rotation, 30 days)
- Console: stdout
- Level: configurable via `log_level` in config
