# 💰 Dollar Earning Crypto Bot

Telegram earning bot — referrals, daily bonuses, channel task verification, withdrawals.  
Stack: **Python 3.11 · python-telegram-bot 21 · asyncpg · PostgreSQL · Railway.app**

---

## 📁 Project Structure

```
earning-bot/
├── main.py                   # Entry point: init DB + register handlers + start polling
├── core/
│   ├── db.py                 # ALL database operations (asyncpg, async functions)
│   └── ui.py                 # Shared keyboards, text helpers, membership checker
├── handlers/
│   ├── start.py              # /start, Home screen
│   ├── tasks.py              # Task list, join verification (get_chat_member)
│   ├── earnings.py           # Balance, daily bonus, leaderboard
│   ├── referral.py           # Share + Refer screens (same invite link)
│   ├── withdraw.py           # Withdrawal ConversationHandler
│   └── admin.py              # /admin panel ConversationHandler
├── requirements.txt
├── Procfile
├── railway.toml
└── .env.example
```

---

## 🚀 Deploy to Railway.app

### Step 1 — Push to GitHub

```bash
cd earning-bot
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/earning-bot.git
git push -u origin main
```

### Step 2 — Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Select **Deploy from GitHub** → pick your repo

### Step 3 — Add PostgreSQL

1. In your project → **New** → **Database** → **Add PostgreSQL**
2. Railway automatically injects `DATABASE_URL` into your service — you don't need to set it manually

### Step 4 — Set Environment Variables

In your **bot service** → **Variables**, add:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | From BotFather |
| `BOT_USERNAME` | `Dollar_Earning_Crypto_Bot` (no @) |
| `BOT_NAME` | `Dollar Earning Bot` |
| `ADMIN_IDS` | Your Telegram user ID (get from [@userinfobot](https://t.me/userinfobot)) |
| `MIN_WITHDRAW` | `20.0` |

### Step 5 — Deploy

Railway auto-deploys on every push. Watch logs in the dashboard.

---

## ⚙️ Adding Tasks (Channels/Groups to Join)

**Important setup:** The bot must be an **admin** (with member visibility) in every channel/group you add as a task, otherwise membership verification will fail.

### Via Telegram Admin Panel

1. Message your bot `/admin`
2. Tap **📋 Manage Tasks** → **➕ Add New Task**
3. Follow the 3-step prompt:
   - Task title (e.g. "Join Our Announcement Channel")
   - Channel/group: `@MyChannel` or `-1001234567890`
   - Invite link: `https://t.me/mychannel`

### Finding a Private Group's Chat ID

Forward any message from the group to [@getidsbot](https://t.me/getidsbot).

---

## 🤖 Bot Flow

```
/start
  │
  ├─ New user → register in DB (store referral if present)
  │
  └─ Show Home screen
       │
       └─ [Tasks] → list all active channel tasks with live ✅/❌ status
            │
            └─ Tap task → Join button + "I Joined" button
                 │
                 └─ Bot calls get_chat_member() to verify
                      │
                      ├─ Not verified → show error + retry
                      │
                      └─ Verified → mark complete in DB
                           │
                           └─ All tasks done? → unlock user
                                │
                                └─ Referrer had referred this user?
                                     → Credit referrer $0.40 + notify them
```

---

## 💡 Key Design Decisions

**PostgreSQL over SQLite** — Railway offers managed Postgres as a free addon. No volumes needed, handles concurrent async writes safely, proper for production.

**Referral credits after tasks** — Prevents fake accounts from being created just to farm referral rewards. Referrer only gets $0.40 once the referred user genuinely completes all tasks.

**Parallel membership checks** — `core/ui.py:check_all_tasks()` uses `asyncio.gather()` to verify all channels simultaneously, not sequentially.

**Withdrawal under development** — The `enter_destination()` handler shows a "feature under development" message. When ready to go live, uncomment the `db.create_withdrawal()` call and remove the placeholder message.

---

## 🔧 Going Live with Withdrawals

In `handlers/withdraw.py`, find the `# ── UNDER DEVELOPMENT ──` block and replace it with:

```python
wid = await db.create_withdrawal(user_id, amount, method_label, dest)
await _notify_admin_withdrawal(context.bot, user_id, amount, method_label, dest)
text = (
    f"✅ *Withdrawal Requested!*\n\n"
    f"💵 Amount: *{fmt_balance(amount)}*\n"
    f"📤 Method: *{method_label}*\n"
    f"🔑 To: `{dest}`\n\n"
    f"⏳ Processing within 24–48 hours."
)
```

---

## 📊 Admin Commands

| Command | Description |
|---|---|
| `/admin` | Open admin panel |
| 📋 Manage Tasks | Add / toggle / delete channel tasks |
| 💸 Withdrawals | Approve or reject pending withdrawal requests |
| 📢 Broadcast | Send a message to all users |
| 📊 Full Stats | Users, active users, balance owed, pending withdrawals |
