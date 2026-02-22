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
  cookie_file_path: "/app/config/hdhive.json"
  server_action_login: "60117d32a5f428137a3759c2470ea04fd5bc035e45"
  server_action_encrypt: "4009ae744a7d94ccc9b0f0ff4e3f5bc55d39a111ad"
  server_action_decrypt: "40c9c3d9fd41a3ddb01539b93b112ebf0dd6e5f98f"
  next_action_first: ""      # legacy fallback
  next_action_second: ""     # legacy fallback
  next_action_unlock: ""     # legacy fallback
  login_next_action: ""      # legacy fallback
```
- Login is always required; resolver auto-login runs when a resource page indicates expired or missing auth.
- Cookie is persisted to `cookie_file_path` and merged from all `Set-Cookie` responses, so next run can reuse session.
- Unlock check is threshold-based: when required points are greater than or equal to `unlock_threshold`, resolver stops instead of spending credits.
- `server_action_*` drives the current HDHive workflow; `next_action_*` / `login_next_action` are kept for compatibility fallback paths.
- If configured `server_action_*` becomes stale after site deploy, resolver can auto-discover latest IDs from current page chunk scripts at runtime.
