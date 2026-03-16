# 💰 Dollar Earning Crypto Bot

Telegram earning bot — signup bonuses, task rewards, referrals, daily bonuses, channel task verification, and withdrawals.  
Stack: **Python 3.11 · python-telegram-bot 21 · asyncpg · PostgreSQL · Railway.app**

---

## 🌟 Features

| Feature | Details |
|---|---|
| 🎉 Signup Bonus | New users receive a configurable bonus (default **$1.00**) on first `/start` |
| 📋 Task Rewards | Each completed channel task pays a configurable reward (default **$0.30**) |
| 👥 Referral Rewards | **2-tier system** — first 5 referrals earn **$0.30** each, then **$0.05** each (all configurable from admin) |
| 🎁 Daily Bonus | **2-tier system** — first 5 days earn **$0.20**, then **$0.02** (all configurable). Missed days cannot be reclaimed |
| 📜 Earn/Referral History | Full transaction history with masked Telegram IDs for privacy |
| 🏆 Leaderboard | Weekly invite rank + overall balance rank |
| 💸 Withdrawals | TON (Crypto), USDT (Crypto), Telegram Stars, PayPal — admin review required |
| 🔧 Admin Panel | Full management of tasks, withdrawals, broadcasts, and **all 8 configurable reward settings** |

---

## 📁 Project Structure

```
usd-bot/
├── main.py                   # Entry point: init DB + register handlers + start polling
├── core/
│   ├── db.py                 # ALL database operations (asyncpg, async functions)
│   └── ui.py                 # Shared keyboards, text helpers, membership checker
├── handlers/
│   ├── start.py              # /start, Home screen
│   ├── tasks.py              # Task list, join verification (get_chat_member)
│   ├── earnings.py           # Balance, daily bonus, leaderboard, history
│   ├── referral.py           # Share + Refer screens (invite link + stats)
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
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/usd-bot.git
git push -u origin main
```

### Step 2 — Create Railway Project

1. Go to [railway.app](https://railway.app) → **New Project**
2. Select **Deploy from GitHub** → pick your repo

### Step 3 — Add PostgreSQL

1. In your project → **New** → **Database** → **Add PostgreSQL**
2. Railway automatically injects `DATABASE_URL` — no manual config needed

### Step 4 — Set Environment Variables

In your **bot service** → **Variables**, add:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | From BotFather |
| `BOT_USERNAME` | Your bot's username (no @) |
| `BOT_NAME` | Display name for the bot |
| `ADMIN_IDS` | Comma-separated Telegram user IDs of admins (e.g. `123456,789012`) |
| `MIN_WITHDRAW` | Minimum balance to withdraw (default `20.0`) |

> **Tip:** Get your Telegram user ID from [@userinfobot](https://t.me/userinfobot)

### Step 5 — Deploy

Railway auto-deploys on every `git push`. Watch logs in the Railway dashboard.

---

## 🤖 Bot Flow

```
/start
  │
  ├─ New user → register in DB (store referral if present)
  │   └─ Credit signup bonus → notify user
  │
  └─ Show Home screen
       │
       └─ [Tasks] → list all active channel tasks with live ✅/❌ status
            │
            └─ Tap task → Join button + "I Joined" button
                 │
                 └─ Bot calls get_chat_member() to verify membership
                      │
                      ├─ Not a member → show error + retry
                      │
                      └─ Verified → mark complete → credit task reward → notify user
                           │
                           └─ All tasks done? → unlock user
                                │
                                └─ Referred by someone?
                                     → Credit referrer reward + notify them

Withdrawals:
  User Withdraw → pick method (TON / USDT / Telegram Stars / PayPal)
               → enter address/username/email
               → request logged as pending
               → Admin reviews in /admin panel
               → Approve (notify user ✅) or Reject with reason (notify user ❌ + refund balance)
```

---

## ⚙️ Adding Tasks

The bot must be an **admin** (with member visibility) in every channel/group you add as a task.

1. Message your bot `/admin`
2. Tap **📋 Manage Tasks** → **➕ Add New Task**
3. Follow the 3-step prompt:
   - Task title (e.g. "Join Our Announcement Channel")
   - Channel/group: `@MyChannel` or `-1001234567890`
   - Invite link: `https://t.me/mychannel`

> **Finding a Private Group's Chat ID:** Forward any message from the group to [@getidsbot](https://t.me/getidsbot)

---

## 🔧 Admin Panel

| Command / Button | Description |
|---|---|
| `/admin` | Open admin panel |
| 📋 Manage Tasks | Add, toggle, or delete channel tasks |
| 💸 Withdrawals | Review pending requests — Mark Paid or Reject with a reason |
| 📢 Broadcast | Send a message to all users |
| 📊 Full Stats | Total users, active users, balance owed, pending withdrawals, top earners |
| ⚙️ Settings | Edit all 8 reward settings (see below) |

### Configurable Settings (via Admin Panel)

All reward amounts and tier thresholds are editable at runtime from the admin `⚙️ Settings` menu — no redeployment needed.

| Setting | Default | Description |
|---|---|---|
| Signup Bonus | `$1.00` | One-time bonus when a new user joins |
| Task Reward | `$0.30` | Per completed channel task |
| Daily Bonus Primary | `$0.20` | Daily bonus for the first N claims |
| Daily Bonus Secondary | `$0.02` | Daily bonus after threshold |
| Daily Bonus Threshold | `5` | Number of days at the primary rate |
| Referral Reward Primary | `$0.30` | Referral reward for the first N invites |
| Referral Reward Secondary | `$0.05` | Referral reward after threshold |
| Referral Reward Threshold | `5` | Number of referrals at the primary rate |

### Admin Privileges

Admins (any user ID listed in `ADMIN_IDS`) have special privileges:
- **Withdrawal bypass** — Admins skip the minimum balance requirement, task prerequisite check, and the 15-day cooldown when withdrawing (useful for testing).

---

## 💡 Key Design Decisions

**PostgreSQL over SQLite** — Railway offers managed Postgres as a free addon. No volumes needed, handles concurrent async writes safely, correct for production.

**Signup bonus credited immediately** — New users receive their bonus the first time they send `/start`. This is logged as a `signup` transaction.

**Task rewards on completion** — Each channel join is rewarded individually via a `task` transaction record.

**Referral credits after tasks** — Prevents fake accounts from being created just to farm referral rewards. Referrer only earns once the referred user genuinely completes all tasks.

**2-tier reward decay** — Daily bonus and referral rewards use a tiered system: the first N claims/referrals pay a higher "primary" rate, after which users earn a lower "secondary" rate. This drives aggressive early sharing while making it hard to reach the withdrawal minimum without extensive referrals. All tier values and thresholds are editable from the admin panel.

**Daily bonus strict** — If a user misses claiming their daily bonus on a given day, that day's bonus cannot be claimed retroactively. This incentivizes daily engagement.

**Configurable amounts at runtime** — All 8 reward settings (signup, task, daily primary/secondary/threshold, referral primary/secondary/threshold) are stored in the `settings` DB table and editable from the admin panel without redeploying.

**Withdrawal queue** — Withdrawals are stored as `pending` in the DB and must be manually approved by an admin. On rejection, balance is automatically refunded and the user is notified with the rejection reason.

**Parallel membership checks** — `core/ui.py:check_all_tasks()` uses `asyncio.gather()` to verify all channels simultaneously.
