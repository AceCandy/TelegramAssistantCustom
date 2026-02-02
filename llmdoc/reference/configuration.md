# Configuration Reference

## Config File Location

`config/config.yaml` - Created on first run with defaults.

## Web Configuration Interface

The configuration can be managed via a web-based dashboard instead of manual YAML editing.
- **Start**: `python main.py --web`
- **Access**: `http://127.0.0.1:12321` (default port)
- **Features**: Validation, dynamic lists for transfers and schedules, modern dark UI.

## Loading Logic

`src/config/config_loader.py:load_config()`:
- Merges user config with defaults
- Auto-adds missing keys and saves back
- Validates required fields (api_id, api_hash, bot_token)

## Required Fields

| Field | Description | Source |
|-------|-------------|--------|
| `api_id` | Telegram API ID | https://my.telegram.org |
| `api_hash` | Telegram API Hash | https://my.telegram.org |
| `bot_account.token` | Bot token | @BotFather |

## Configuration Sections

### API Credentials
- `api_id`, `api_hash`: Required for all clients

### User Account (Optional)
```yaml
user_account:
  enabled: false          # Enable user client
  phone: ""               # Phone number for login
  session_name: "user_session"
```
Required for: message transfer, scheduled messages

### Bot Account
```yaml
bot_account:
  token: ""               # Bot token
  session_name: "bot_session"
```

### Download Settings
```yaml
youtube_download:
  format: "bv*+ba/best"   # yt-dlp format
  cookies: ""             # For premium content
  download_list: false    # Download playlists

douyin:
  cookie: ""

bilibili:
  cookie: ""
```

### Message Transfer
```yaml
transfer_message:
  - source_chat: ""       # Source ID or username
    target_chat: ""       # Target ID or username
    include_keywords: []  # Only forward if contains
    exclude_words: []     # Don't forward if contains (priority)
    forwardIgnoreLink: [] # Strip links matching domains
```

### Scheduled Messages
```yaml
scheduled_messages:
  - chat_id: ""
    message: ""
    time: "08:00"         # 24h format, daily
```

### Permission Control
```yaml
allowed_chat_ids: []      # Empty = allow all
```
Logs unauthorized attempts with chat_id for easy whitelisting.

### Proxy
```yaml
proxy:
  enabled: false
  host: "127.0.0.1"
  port: 7890
```
Only SOCKS5 supported.

### HDHive (Advanced)
```yaml
hdhive:
  username: ""
  password: ""
  unlock_threshold: 20
  user_agent: "..."
  next_action_first: ""
  next_action_second: ""
  next_action_unlock: ""
  login_next_action: ""
```
