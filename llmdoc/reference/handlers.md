# Handler Reference

## EventHandler - Central Router

**File**: `src/handlers/event_handler.py`

### Registration Methods

| Method | Purpose |
|--------|---------|
| `register_handlers(bot_client)` | Registers `/start` and message handlers on bot |
| `register_message_transfer(user_client)` | Registers message transfer handlers on user client |

### Message Routing

`handle_message(event)` routes based on content:
1. Check `is_chat_allowed()` for permission
2. Detect URL patterns → delegate to platform handler
3. Check for media attachments → delegate to TelegramHandler

### Key Methods

- `is_chat_allowed(chat_id)` - Checks against `allowed_chat_ids` config
- `get_entity_safely(client, entity_id)` - Safe entity lookup with error handling
- `send_video_to_user(event, file_path)` - Unified file sending with cleanup

---

## TelegramHandler

**File**: `src/handlers/telegram_handler.py`

Downloads media from Telegram messages. Categorizes files:
- Videos → `downloads/telegram/videos/`
- Audio → `downloads/telegram/audios/`
- Photos → `downloads/telegram/photos/`
- Others → `downloads/telegram/others/`

---

## YouTubeHandler

**File**: `src/handlers/youtube_handler.py`

Uses yt-dlp for downloads. Features:
- Format selection via config
- Cookie support for premium content
- Playlist handling (configurable)
- Audio conversion option

Temp → `temp/youtube/`, Final → `downloads/youtube/`

---

## DouyinHandler

**File**: `src/handlers/douyin_handler.py`

Downloads Douyin (抖音) videos. Custom implementation.

---

## BilibiliHandler

**File**: `src/handlers/bilibili_handler.py`

Downloads Bilibili (B站) videos. Uses cookies for auth.

Temp → `temp/bilibili/`, Final → `downloads/bilibili/`

---

## HDHiveResolver

**File**: `src/handlers/hdhive_handler.py`

HDHive resolver now follows direct-page-first + server-action flow:
- Supports `hdhive.com` and `hdhive.online` links.
- Opens resource page directly first, then tries direct `115`/`115cdn` link extraction.
- If login is required, triggers `_re_login()` via server-action login and persists merged cookies.
- If direct extraction fails, uses `_action1_get_query()` to encrypt query payload, then calls go-api URL endpoint.
- Decrypts returned payload with `_server_action_decrypt()` and assembles final 115 link (including password/access code when needed).
- If unlock is required, compares points with `unlock_threshold`; only unlocks when below threshold, then retries resource fetch.

Key methods for this flow:
- `resolve_url()`
- `_re_login()`
- `_action1_get_query()`
- `_go_api_get_data_str()`
- `_go_api_unlock()`
- `_server_action_decrypt()`

Cookie behavior:
- Loads cookie from disk before requests.
- Merges new `Set-Cookie` values into existing cookie set.
- Saves updated cookie after login and subsequent responses for session reuse.

---

## ChannelTransferHandler

**File**: `src/handlers/channel_transfer_handler.py`

Handles message forwarding between channels:
- Keyword filtering (include/exclude)
- Link domain filtering
- Media handling
