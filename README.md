# 💰 Dollar Earning Crypto Bot

Telegram earning bot — signup bonuses, task rewards, referrals, daily bonuses, leaderboards, group auto-promoter, and admin-managed withdrawals.  
Stack: **Python 3.12 · python-telegram-bot 21 (job-queue) · asyncpg · PostgreSQL · Railway.app**

---

## 🌟 Features

| Feature | Details |
|---|---|
| 🎉 Signup Bonus | New users receive a configurable bonus (default **$1.00**) on first `/start` |
| 📋 Task Rewards | Each completed channel task pays a configurable reward (default **$0.30**) |
| 👥 Referral System | **2-tier system** — first 5 referrals earn **$0.30** each, then **$0.05** (all admin-configurable) |
| 🎁 Daily Bonus | **2-tier system** — first 5 days earn **$0.20**, then **$0.02**. Requires **2 invites per week** to unlock |
| ⏰ Daily Bonus Reminder | Bot automatically DMs users every day at **10:00 UTC** if they haven't claimed their bonus |
| 🏆 Leaderboard | Weekly Top 5 Inviters & Full Leaderboard with Prize Pool display |
| 🎭 Fake Leaderboard | Pre-seeded **50 localized fake users** make the leaderboard look active on launch. Toggle ON/OFF from admin |
| 📢 Group Auto-Promoter | Group owners can add the bot to their groups and configure auto-posting of their referral link at a custom interval |
| 📜 Transaction History | Full earning history with privacy-masked Telegram IDs |
| 💸 Withdrawals | TON, USDT, Telegram Stars, PayPal — admin review + reject-with-reason + auto-refund |
| 🛡️ Support Tickets | Users can submit feedback/complaints via the FAQ menu. Admins review, reply via Push Notifications, and resolve in `/admin`. |
| 🌍 Profile Countries | Users can select their real country (including sanctioned countries like Iran/Syria) which displays on their active profile. |
| 🎰 Lucky Draw | Daily draw where users pay Telegram Stars (50/100/150/300) to enter. 3 winners selected daily at UTC midnight. |
| 🔧 Admin Panel | Tasks, withdrawals, broadcast, tickets, full stats (**real users only**), and all configurable reward settings |
| 📊 Full Stats (Admin) | Accurate view of real user counts, balance owed, top inviters/earners — fake users fully excluded |

---

## 📁 Project Structure

```
usd-bot/
├── main.py                   # Entry point: init DB, register handlers, schedule jobs, start polling
├── core/
│   ├── db.py                 # ALL database operations (asyncpg, async functions)
│   └── ui.py                 # Shared keyboards, text helpers, membership checker
├── handlers/
│   ├── start.py              # /start, Home screen
│   ├── tasks.py              # Task list, join verification (get_chat_member)
│   ├── earnings.py           # Balance, daily bonus, leaderboard, history
│   ├── referral.py           # Share + Refer screens (invite link + stats)
│   ├── withdraw.py           # Withdrawal ConversationHandler
│   ├── admin.py              # /admin panel ConversationHandler
│   └── groups.py             # Group Owner Auto-Promoter settings UI
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
  └─ Show Home screen with inline nav keyboard
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

Daily Bonus:
  User taps claim → check if ≥2 new referrals this week
                 ├─ Not enough invites → show progress (e.g. "1/2 invites this week")
                 └─ Eligible → credit tiered daily bonus

Daily Reminder Job (10:00 UTC):
  Bot scans all users with unclaimed bonus → DMs each one
  (with 50ms delay between to respect Telegram rate limits)

Lucky Draw:
  User taps "🎰 Lucky Draw"
  → Selects 50/100/150/300 Stars
  → Pays via Native Telegram XTR Invoice
  → Added to daily draw pool
  
Lucky Draw Resolution (23:59 UTC):
  Bot randomly selects 3 Fake Users as winners for $30, $70, $200
  → Notifies all real users who entered today to check the board

Withdrawals:
  User Withdraw → pick method (TON / USDT / Telegram Stars / PayPal)
               → enter address/username/email
               → request logged as pending
               → Admin reviews in /admin panel
               → Approve (notify user ✅) or Reject with reason (notify user ❌ + refund balance)

Group Auto-Promoter:
  Owner adds bot to their Telegram group (as admin)
  → Bot detects via NEW_CHAT_MEMBERS event → registers group under owner
  → Owner DM'd with setup instructions
  → Owner opens "👥 For Group Owners" in private chat
  → Can set interval (1h / 3h / 6h / 12h / 24h) and toggle ON/OFF per group
  → Background job runs every 5 min → posts referral link in due groups
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

You can also **edit** the title, chat ID, or link of existing tasks, and **activate/deactivate** them at any time from the task detail screen.

> **Finding a Private Group's Chat ID:** Forward any message from the group to [@getidsbot](https://t.me/getidsbot)

---

## 🔧 Admin Panel

| Command / Button | Description |
|---|---|
| `/admin` | Open admin panel |
| 📋 Manage Tasks | Add, edit, toggle, or delete channel tasks |
| 💸 Withdrawals | Review pending requests — Mark Paid or Reject with a reason |
| 📢 Broadcast | Send a message to all users |
| 📊 Full Stats | Real-users-only stats: total users, active users, balance owed, top inviters/earners |
| ⚙️ Settings | Edit all reward settings + toggle Fake Leaderboard |

### Configurable Settings (via Admin Panel ⚙️)

All reward amounts and thresholds are editable at runtime — no redeployment needed.

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
| Fake Leaderboard | `ON` | Show/hide pre-seeded fake users in leaderboards |

### Admin-Only Commands

| Command | Description |
|---|---|
| `/admin` | Open admin panel |
| `/reseed_fake` | Wipe and re-generate the 50 fake leaderboard users with new random stats |
| `/test_daily_job` | Manually trigger the daily bonus reminder broadcast |
| `/addbalance` | Give unearned balance to a specific user id (`/addbalance 12345 5.50`) |
| `/deductbalance` | Revoke a specific user id's balance (`/deductbalance 12345 2.00`) |
| `/setbalance` | Forcibly set a specific user id's balance to an exact amount (`/setbalance 12345 10.00`) |

### Admin Privileges

Admins (any user ID listed in `ADMIN_IDS`) have special privileges:
- **Withdrawal bypass** — skip minimum balance, task prerequisite, and 15-day cooldown (useful for testing).

---

## 📢 Group Auto-Promoter

Group owners can use the bot to automatically promote their referral link inside their Telegram groups.

### How it works:
1. Add the bot to your Telegram group and make it an **Administrator**
2. The bot detects it was added and sends you a DM confirming the registration
3. Open the bot in private chat → tap **👥 For Group Owners**
4. Select your group and configure:
   - **Auto-post interval**: 1h / 3h / 6h / 12h / 24h
   - **Toggle**: Enable or Pause auto-posting per group
   - **Remove**: Stop the bot from posting in a specific group

### Notes:
- The bot posts a referral promo message with your referral link at the chosen interval
- If the bot is kicked from a group, the group is automatically removed from the system
- A background job runs every 5 minutes to check which groups are due for a post

---

## 🎭 Fake Leaderboard

To make the bot look active before you have real users, 50 pre-seeded fake users are stored in the database with realistic localized names and a power-law invite distribution (most have ~100 invites, a few have thousands).

- Fake users are **never shown** in the Admin Panel — stats always show real data only
- The weekly Top 5 shuffles a random subset weekly (based on week number) for variety
- Toggle ON/OFF at any time from **Admin → ⚙️ Settings → Fake Leaderboard**
- Use `/reseed_fake` to regenerate all fake users with fresh randomized data

---

## 💡 Key Design Decisions

**Referral credits after tasks** — Prevents fake accounts from farming referral rewards. Referrer only earns once the referred user completes all tasks.

**Weekly invite requirement for daily bonus** — Users must invite ≥2 real users each week to unlock daily claims, driving ongoing organic growth.

**2-tier reward decay** — Both daily and referral rewards use a tiered system (primary → secondary rate after N claims). Drives aggressive early sharing while keeping economics sustainable.

**Daily strict** — Missed daily bonuses cannot be reclaimed retroactively. Incentivizes daily engagement.

**Daily reminder broadcast** — At 10:00 UTC daily, the bot automatically notifies all users who haven't yet claimed their bonus, with a safe 50ms delay between messages to stay within Telegram rate limits.

**Configurable at runtime** — All 9 reward settings are stored in the `settings` DB table and editable from the admin panel — no redeployment needed.

**Withdrawal queue** — Withdrawals are stored as `pending` and must be manually approved. On rejection, balance is automatically refunded and the user is notified.

**Parallel membership checks** — `core/ui.py:check_all_tasks()` uses `asyncio.gather()` to verify all channels simultaneously.

**Admin stats exclude fake users** — The `📊 Full Stats` screen always bypasses the `show_fake_leaders` toggle so admins see accurate growth metrics.
