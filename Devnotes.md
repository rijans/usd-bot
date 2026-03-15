# Dollar Earning Crypto Bot — Developer Notes

## Project Structure
```
usd-bot/
├── main.py                   # Entry point + all handler registration
├── core/
│   ├── db.py                 # ALL database operations (asyncpg + PostgreSQL)
│   └── ui.py                 # Shared keyboards, helpers, membership checker
├── handlers/
│   ├── start.py              # /start, Home screen, Reply keyboard
│   ├── tasks.py              # Task list + channel join verification
│   ├── earnings.py           # Balance, daily bonus, leaderboard
│   ├── referral.py           # Share + Refer screens
│   ├── withdraw.py           # Withdrawal ConversationHandler
│   └── admin.py              # /admin panel ConversationHandler
├── requirements.txt
├── Procfile
└── railway.toml
```

---

## Known Bugs / TODO

### High Priority

### Medium Priority

### Low Priority

---

## Architecture Notes

### Handler Pattern
Every handler function signature:
```python
async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
```
- Inline button press  → `update.callback_query` is set, `update.message` is None
- Reply keyboard press → `update.message` is set,    `update.callback_query` is None
- Slash command        → `update.message` is set,    `update.callback_query` is None

Always check which one you have before calling `.answer()` or `.reply_text()`.

### ConversationHandler States
- Withdraw flow:  PICK_METHOD(1) → ENTER_DEST(2)
- Admin add task: ADD_TASK_TITLE(20) → ADD_TASK_CHAT(21) → ADD_TASK_LINK(22)
- Admin broadcast: BROADCAST_TEXT(30)
State numbers must be unique across ALL ConversationHandlers in the app.

### Database
- All DB calls are async via asyncpg connection pool
- Pool is lazily initialized on first call to `get_pool()`
- Always use `async with pool.acquire() as conn:` — never hold connections
- Transactions: `async with conn.transaction():` for multi-step operations
- Schema is idempotent (`CREATE TABLE IF NOT EXISTS`) — safe to run on every startup

### Telegram API Limits
- `edit_message_text` fails with BadRequest if content is identical → silenced in error_handler
- `get_chat_member` requires bot to be admin in private channels/groups
- Inline keyboards: buttons in same list[] = same row, separate list[] = new row
- `switch_inline_query` on a button opens share sheet (used for referral sharing)

---

## Environment Variables
| Variable         | Description                          | Example                    |
|------------------|--------------------------------------|----------------------------|
| BOT_TOKEN        | From BotFather                       | 123456:ABCdef...           |
| BOT_USERNAME     | Without @                            | Dollar_Earning_Crypto_Bot  |
| BOT_NAME         | Display name                         | Dollar Earning Crypto Bot  |
| ADMIN_IDS        | Comma-separated Telegram user IDs    | 123456789,987654321        |
| DATABASE_URL     | Auto-injected by Railway Postgres     | postgresql://...           |
| MIN_WITHDRAW     | Minimum withdrawal amount            | 20.0                       |

---

## Deployment (Railway)
- Push to GitHub → Railway auto-deploys
- Logs: Railway dashboard → your service → Deploy Logs
- DB: Railway → Postgres service → Data tab (view tables/rows directly)
- Restart: Railway → your service → Deployments → Restart

## Local Development
```bash
# Install deps
pip install python-telegram-bot==21.5 asyncpg==0.29.0

# Set env vars
export BOT_TOKEN=your_token
export DATABASE_URL=postgresql://localhost/botdb
export ADMIN_IDS=your_telegram_id

# Run
python main.py
```