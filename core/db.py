"""
core/db.py  ─  Async PostgreSQL connection pool (asyncpg)

All SQL is here. Handlers import functions, never write raw SQL.
Railway: add the Postgres plugin → DATABASE_URL is injected automatically.
"""
import os
import asyncpg
from typing import Optional

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        url = os.environ["DATABASE_URL"]
        # Railway injects postgres:// but asyncpg needs postgresql://
        url = url.replace("postgres://", "postgresql://", 1)
        _pool = await asyncpg.create_pool(url, min_size=2, max_size=10)
    return _pool


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ─────────────────────────────────────────────────────────────────────────────
# Schema bootstrap
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id         BIGINT      PRIMARY KEY,
    username        TEXT,
    full_name       TEXT        NOT NULL,
    balance         NUMERIC(10,2) NOT NULL DEFAULT 0,
    total_invites   INT         NOT NULL DEFAULT 0,
    referred_by     BIGINT      REFERENCES users(user_id),
    tasks_done      BOOLEAN     NOT NULL DEFAULT FALSE,
    last_daily      DATE,
    last_withdraw   TIMESTAMPTZ,
    banned          BOOLEAN     NOT NULL DEFAULT FALSE,
    joined_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tasks (
    id              SERIAL      PRIMARY KEY,
    title           TEXT        NOT NULL,
    chat_id         TEXT        NOT NULL UNIQUE,   -- @username or -100xxxxx
    invite_link     TEXT        NOT NULL,
    reward          NUMERIC(10,2) NOT NULL DEFAULT 0,
    position        INT         NOT NULL DEFAULT 0,
    active          BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS task_completions (
    user_id         BIGINT      NOT NULL REFERENCES users(user_id),
    task_id         INT         NOT NULL REFERENCES tasks(id),
    completed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, task_id)
);

CREATE TABLE IF NOT EXISTS withdrawals (
    id              SERIAL      PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(user_id),
    amount          NUMERIC(10,2) NOT NULL,
    method          TEXT        NOT NULL,
    destination     TEXT        NOT NULL,
    status          TEXT        NOT NULL DEFAULT 'pending',  -- pending|paid|rejected
    requested_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at    TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS transactions (
    id              SERIAL      PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(user_id),
    amount          NUMERIC(10,2) NOT NULL,
    type            TEXT        NOT NULL, -- e.g., 'signup', 'task', 'referral', 'daily_bonus'
    related_to      TEXT,       -- e.g., user_id of referral, or task_id
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS settings (
    key             TEXT        PRIMARY KEY,
    value           TEXT        NOT NULL
);

CREATE TABLE IF NOT EXISTS promoted_groups (
    chat_id         BIGINT      PRIMARY KEY,
    title           TEXT        NOT NULL DEFAULT '',
    owner_id        BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    interval_hours  INT         NOT NULL DEFAULT 1,
    active          BOOLEAN     NOT NULL DEFAULT TRUE,
    last_posted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id         BIGINT      PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    email           TEXT,
    phone           TEXT,
    bio             TEXT,
    ton_address     TEXT,
    usdt_address    TEXT,
    paypal_email    TEXT,
    stars_username  TEXT,
    alt_username    TEXT,
    country         TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS tickets (
    id              SERIAL      PRIMARY KEY,
    user_id         BIGINT      REFERENCES users(user_id) ON DELETE CASCADE,
    message         TEXT        NOT NULL,
    reply           TEXT,
    status          TEXT        NOT NULL DEFAULT 'open', -- 'open', 'answered', 'closed'
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lucky_draw_entries (
    id              SERIAL      PRIMARY KEY,
    user_id         BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    stars_paid      INT         NOT NULL,
    draw_date       DATE        NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lucky_draw_winners (
    id              SERIAL      PRIMARY KEY,
    draw_date       DATE        NOT NULL UNIQUE DEFAULT CURRENT_DATE,
    winner_1_id     BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    winner_2_id     BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    winner_3_id     BIGINT      NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    prize_1         TEXT        NOT NULL DEFAULT '200',
    prize_2         TEXT        NOT NULL DEFAULT '70',
    prize_3         TEXT        NOT NULL DEFAULT '30',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

async def init_schema():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
        
        # Add reject_reason column for backward compatibility
        await conn.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS reject_reason TEXT;")
        
        # Add country column for backward compatibility
        await conn.execute("ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS country TEXT;")
        
        # Insert defaults if empty
        await conn.execute(
            """INSERT INTO settings (key, value)
               VALUES ('signup_bonus', '1.00'),
                      ('task_reward', '0.30'),
                      ('daily_bonus_primary', '0.20'),
                      ('daily_bonus_secondary', '0.02'),
                      ('daily_bonus_threshold', '5'),
                      ('referral_reward_primary', '0.30'),
                      ('referral_reward_secondary', '0.05'),
                      ('referral_reward_threshold', '5'),
                      ('show_fake_leaders', '1')
               ON CONFLICT (key) DO NOTHING"""
        )

        # Seed fake users if they don't exist
        # We use negative user_ids (-1001 to -1050)
        import random
        fake_count = await conn.fetchval("SELECT COUNT(*) FROM users WHERE user_id < 0")
        if fake_count == 0:
            names = [
                "🍷🌹™👉●×Hejran🌙🫧", "⚜༒🦋𝔖𝔞𝔯𝔞🦋༒⚜", "⌜JERRY TWO BOT⌟", "🌙🌙💦ད☘🏹🌙❤️Nadia ❤️🌙🎲", 
                "🥀Yasmin 🇵🇸", "SangMata (beta)", "Luis Nano", "Harqaboobe", "Coco Rs", "El Ator", 
                "39801 Pedro", "Miki Yema", "Adrian Adrian", "Gooni", "Diallo Oury", "eranda weeraratne", 
                "Lionoftheyear 20", "Belal3mad", "Shshshsh Fjfjcjfjfj", "🇮🇷Rumi Zahara🦋 💖", 
                "⌜✨🌿 Subhashini↔വീഡിയോക്കോൾ↔🌺", "Jax stuff Collection", "Aakanshi • கோயம்புத்தூர்", 
                "Purnima Singh 💫", "Anjali...💋", "Rahul", "Priya❤️", "Ivan", "Anna🔥", "Dmitry", "Ahmed🇪🇬", 
                "Fatima", "Aisha", "Muhammad", "Ayesha", "Bilal", "Youssef", "Mona", "Nguyen", "Tran🍓", 
                "Budi", "Siti", "Silva", "Santos", "Kim", "Lee", "Park", "Alex", "Jordan", "Moon_light",
                "Rozana", "Loula", "safia", "Rose", "Group Help", "Ⓜ️aqsuda 🍉📜📚🤲🏼", "Sizzle", 
                "^=F A M O s §} {F A M O?", "/ !", "Nes", "Saray", "Ken Yow", "Sagar", "Galiya Shostakovich",
                "Amelia", "Adi Dxb", "Liya", "Phancy Casey", "Atlas", "Meena Khan", "m a", "Mery Alex",
                "Averse Ta", "Mehde Hassan", "Iron Man", "Lambozz", "Memkk", "Ganesh Hyderabad NSUI",
                "Akith Ahsan", "Dark DEVIL🦅👑", "Edward Elric", "Dipro H", "Wasimkhan☪️☪️"
            ]
            
            rng = random.Random(42)
            
            for i in range(50):
                uid = -1001 - i
                name = rng.choice(names)
                
                # Pick an invite tier to simulate a power-law distribution
                tier = rng.choices(
                    population=["low", "mid", "high", "viral"], 
                    weights=[0.60, 0.25, 0.10, 0.05], 
                    k=1
                )[0]
                
                if tier == "low":
                    invites = rng.randint(50, 150)
                elif tier == "mid":
                    invites = rng.randint(151, 500)
                elif tier == "high":
                    invites = rng.randint(501, 2000)
                else: # viral
                    invites = rng.randint(2001, 8000)
                    
                # Calculate realistic balance matching our reward model 
                # ($1 signup + ~$1.5 tasks + daily bonuses + tiered referral)
                base_bal = 4.0 # signup + early tasks + couple daily
                if invites <= 5:
                    bal = base_bal + (invites * 0.30)
                else:
                    bal = base_bal + (5 * 0.30) + ((invites - 5) * 0.05)
                
                # Add a few random extra dollars for daily checkins/other tasks
                bal += rng.uniform(0.0, 15.0)
                bal = round(bal, 2)
                
                await conn.execute(
                    """INSERT INTO users (user_id, full_name, username, balance, total_invites, tasks_done)
                       VALUES ($1, $2, $3, $4, $5, TRUE)
                       ON CONFLICT DO NOTHING""",
                    uid, name, f"user_{abs(uid)}", bal, invites
                )


# ─────────────────────────────────────────────────────────────────────────────
# Users
# ─────────────────────────────────────────────────────────────────────────────

async def get_user(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)


async def upsert_user(user_id: int, username: str, full_name: str,
                      referred_by: Optional[int] = None) -> tuple[asyncpg.Record, bool, float]:
    """Insert user if new, return (record, is_new, signup_bonus_credited)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        existing = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if existing:
            # Keep name/username up to date
            await conn.execute(
                "UPDATE users SET username=$2, full_name=$3 WHERE user_id=$1",
                user_id, username or "", full_name
            )
            return await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id), False, 0.0

        # Validate referrer exists and isn't the user themselves
        valid_referrer = None
        if referred_by and referred_by != user_id:
            ref = await conn.fetchrow("SELECT user_id FROM users WHERE user_id=$1", referred_by)
            if ref:
                valid_referrer = referred_by

        async with conn.transaction():
            amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='signup_bonus'")
            signup_bonus = float(amt_str) if amt_str else 0.0
            
            await conn.execute(
                """INSERT INTO users (user_id, username, full_name, balance, referred_by)
                   VALUES ($1, $2, $3, $4, $5)""",
                user_id, username or "", full_name, signup_bonus, valid_referrer
            )
            
            if signup_bonus > 0:
                await conn.execute(
                    """INSERT INTO transactions (user_id, amount, type)
                       VALUES ($1, $2, 'signup')""",
                    user_id, signup_bonus
                )
                
            record = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
            return record, True, signup_bonus


async def add_balance(user_id: int, amount: float, conn=None) -> None:
    """Add (or subtract if negative) from a user's balance."""
    async def _run(c):
        await c.execute(
            "UPDATE users SET balance = balance + $2 WHERE user_id=$1",
            user_id, amount
        )
    if conn:
        await _run(conn)
    else:
        pool = await get_pool()
        async with pool.acquire() as c:
            await _run(c)


async def get_rank(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT COUNT(*)+1 AS rank FROM users WHERE balance > "
            "(SELECT balance FROM users WHERE user_id=$1)",
            user_id
        )
        return row["rank"]


async def get_weekly_invite_rank(user_id: int) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        show_fake = await get_setting("show_fake_leaders", "1")
        if show_fake == "1":
            # Rank includes real users and a subset of fake users (pseudorandom by week)
            # The CTE below mirrors the leaderboard logic
            query = """
            WITH week_seed AS (
                SELECT EXTRACT(WEEK FROM NOW()) AS w
            ),
            eligible_users AS (
                SELECT user_id, total_invites FROM users WHERE user_id > 0
                UNION ALL
                SELECT user_id, total_invites FROM users CROSS JOIN week_seed
                WHERE user_id < 0 
                  AND MOD(ABS(user_id) * week_seed.w::int, 100) < 30
            )
            SELECT COUNT(*)+1 AS rank 
            FROM eligible_users 
            WHERE total_invites > (SELECT COALESCE(total_invites, 0) FROM users WHERE user_id=$1)
            """
            row = await conn.fetchrow(query, user_id)
        else:
            row = await conn.fetchrow(
                "SELECT COUNT(*)+1 AS rank FROM users WHERE user_id > 0 AND total_invites > "
                "(SELECT total_invites FROM users WHERE user_id=$1)",
                user_id
            )
        return row["rank"]


async def get_weekly_referrals(user_id: int) -> int:
    """Returns the number of accurate referrals the user made since Monday of the current week."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            """SELECT COUNT(*) FROM transactions 
               WHERE user_id=$1 AND type='referral' AND created_at >= date_trunc('week', NOW())""",
            user_id
        )

async def get_setting(key: str, default: str) -> str:
    pool = await get_pool()
    async with pool.acquire() as conn:
        val = await conn.fetchval("SELECT value FROM settings WHERE key=$1", key)
        return val if val else default


async def set_setting(key: str, value: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ($1, $2) ON CONFLICT (key) DO UPDATE SET value=$2",
            key, value
        )


async def claim_daily_bonus(user_id: int) -> tuple[bool, str, float]:
    """Returns (success, reason, amount_credited). Uses tiered daily bonus."""
    from datetime import date
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_daily, tasks_done FROM users WHERE user_id=$1", user_id)
        if not row or not row["tasks_done"]:
            return False, "tasks_incomplete", 0.0
        today = date.today()
        if row["last_daily"] and row["last_daily"] >= today:
            return False, "already_claimed", 0.0

        # Enforce weekly referral quota
        weekly_refs = await get_weekly_referrals(user_id)
        if weekly_refs < 2:
            return False, f"needs_invites:{weekly_refs}", 0.0

        # Count previous daily claims for tiered logic
        past_claims = await conn.fetchval(
            "SELECT COUNT(*) FROM transactions WHERE user_id=$1 AND type='daily_bonus'",
            user_id
        )
        threshold = int(await get_setting("daily_bonus_threshold", "5"))
        if past_claims < threshold:
            amount = float(await get_setting("daily_bonus_primary", "0.20"))
        else:
            amount = float(await get_setting("daily_bonus_secondary", "0.02"))

        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET balance=balance+$2, last_daily=$3 WHERE user_id=$1",
                user_id, amount, today
            )
            await conn.execute(
                """INSERT INTO transactions (user_id, amount, type)
                   VALUES ($1, $2, 'daily_bonus')""",
                user_id, amount
            )
            return True, "ok", amount


async def get_all_user_ids() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE banned=FALSE AND user_id > 0")
        return [r["user_id"] for r in rows]


async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users WHERE user_id > 0")
        active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE tasks_done=TRUE AND user_id > 0")
        total_paid = await conn.fetchval("SELECT COALESCE(SUM(balance),0) FROM users WHERE user_id > 0")
        p_w = await conn.fetchval("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
        profs = await conn.fetchval("SELECT COUNT(*) FROM user_profiles")
        return {
            "total_users": total,
            "active_users": active,
            "total_balance_owed": float(total_paid),
            "pending_withdrawals": p_w,
            "profiles_setup": profs,
        }


async def get_leaderboard(limit: int = 20, include_fake: bool = True) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        show_fake = await get_setting("show_fake_leaders", "1")
        if show_fake == "1" and include_fake:
            # Select real users + ~30% of fake users based on week hash
            query = """
            WITH week_seed AS (
                SELECT EXTRACT(WEEK FROM NOW()) AS w
            )
            SELECT user_id, full_name, total_invites, balance 
            FROM users CROSS JOIN week_seed
            WHERE user_id > 0 
               OR (user_id < 0 AND MOD(ABS(user_id) * week_seed.w::int, 100) < 30)
            ORDER BY total_invites DESC LIMIT $1
            """
            return await conn.fetch(query, limit)
        else:
            return await conn.fetch(
                "SELECT user_id, full_name, total_invites, balance "
                "FROM users WHERE user_id > 0 ORDER BY total_invites DESC LIMIT $1",
                limit
            )

async def get_earners_leaderboard(limit: int = 10, include_fake: bool = True) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        show_fake = await get_setting("show_fake_leaders", "1")
        if show_fake == "1" and include_fake:
            query = """
            WITH week_seed AS (
                SELECT EXTRACT(WEEK FROM NOW()) AS w
            )
            SELECT user_id, full_name, total_invites, balance 
            FROM users CROSS JOIN week_seed
            WHERE user_id > 0 
               OR (user_id < 0 AND MOD(ABS(user_id) * week_seed.w::int, 100) < 30)
            ORDER BY balance DESC LIMIT $1
            """
            return await conn.fetch(query, limit)
        else:
            return await conn.fetch(
                "SELECT user_id, full_name, total_invites, balance "
                "FROM users WHERE user_id > 0 ORDER BY balance DESC LIMIT $1",
                limit
            )


async def get_user_history(user_id: int, limit: int = 15) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM transactions WHERE user_id=$1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tasks
# ─────────────────────────────────────────────────────────────────────────────

async def get_active_tasks() -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM tasks WHERE active=TRUE ORDER BY position ASC, id ASC"
        )


async def get_task(task_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM tasks WHERE id=$1", task_id)


async def get_task_by_chat(chat_id: str) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM tasks WHERE chat_id=$1", chat_id)


async def get_completed_task_ids(user_id: int) -> set[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT task_id FROM task_completions WHERE user_id=$1", user_id
        )
        return {r["task_id"] for r in rows}


async def mark_task_complete(user_id: int, task_id: int) -> tuple[bool, float]:
    """Returns (True/False if newly completed, reward_credited)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        try:
            async with conn.transaction():
                await conn.execute(
                    "INSERT INTO task_completions(user_id, task_id) VALUES($1,$2)",
                    user_id, task_id
                )
                
                amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='task_reward'")
                task_reward = float(amt_str) if amt_str else 0.0
                
                if task_reward > 0:
                    await conn.execute(
                        "UPDATE users SET balance=balance+$2 WHERE user_id=$1",
                        user_id, task_reward
                    )
                    await conn.execute(
                        """INSERT INTO transactions (user_id, amount, type, related_to)
                           VALUES ($1, $2, 'task', $3)""",
                        user_id, task_reward, str(task_id)
                    )
                return True, task_reward
        except asyncpg.UniqueViolationError:
            return False, 0.0


async def check_and_finalize_tasks(user_id: int) -> tuple[bool, float]:
    """
    Check if user has completed ALL active tasks.
    If yes, mark tasks_done=TRUE and credit referrer's reward.
    Returns (True if triggered finalization, float reward credited to referrer).
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE user_id=$1", user_id)
        if not user or user["tasks_done"]:
            return False, 0.0

        total_tasks = await conn.fetchval("SELECT COUNT(*) FROM tasks WHERE active=TRUE")
        done_count = await conn.fetchval(
            "SELECT COUNT(*) FROM task_completions tc "
            "JOIN tasks t ON tc.task_id=t.id "
            "WHERE tc.user_id=$1 AND t.active=TRUE",
            user_id
        )

        if done_count < total_tasks:
            return False, 0.0

        ref_amt_credited = 0.0
        
        async with conn.transaction():
            # All tasks done — unlock user
            await conn.execute("UPDATE users SET tasks_done=TRUE WHERE user_id=$1", user_id)
    
            # Credit referrer
            if user["referred_by"]:
                referrer_id = user["referred_by"]
                ref = await conn.fetchrow("SELECT tasks_done, total_invites FROM users WHERE user_id=$1", referrer_id)
                if ref:
                    # Tiered referral reward
                    threshold = int(await conn.fetchval("SELECT COALESCE((SELECT value FROM settings WHERE key='referral_reward_threshold'), '5')"))
                    if ref["total_invites"] < threshold:
                        amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='referral_reward_primary'")
                        ref_amt = float(amt_str) if amt_str else 0.30
                    else:
                        amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='referral_reward_secondary'")
                        ref_amt = float(amt_str) if amt_str else 0.05

                    if ref_amt > 0:
                        await conn.execute(
                            "UPDATE users SET balance=balance+$2, total_invites=total_invites+1 WHERE user_id=$1",
                            referrer_id, ref_amt
                        )
                        await conn.execute(
                            """INSERT INTO transactions (user_id, amount, type, related_to)
                               VALUES ($1, $2, 'referral', $3)""",
                            referrer_id, ref_amt, str(user_id)
                        )
                        ref_amt_credited = ref_amt

            return True, ref_amt_credited


async def add_task(title: str, chat_id: str, invite_link: str,
                   reward: float = 0, position: int = 0) -> asyncpg.Record:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """INSERT INTO tasks (title, chat_id, invite_link, reward, position)
               VALUES ($1,$2,$3,$4,$5) RETURNING *""",
            title, chat_id, invite_link, reward, position
        )


async def toggle_task(task_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE tasks SET active=NOT active WHERE id=$1 RETURNING *", task_id
        )


async def delete_task(task_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute("DELETE FROM task_completions WHERE task_id=$1", task_id)
            result = await conn.execute("DELETE FROM tasks WHERE id=$1", task_id)
            return result == "DELETE 1"


# ─────────────────────────────────────────────────────────────────────────────
# Withdrawals
# ─────────────────────────────────────────────────────────────────────────────

MIN_WITHDRAW = float(os.environ.get("MIN_WITHDRAW", "20.0"))
WITHDRAW_COOLDOWN_DAYS = 15


async def can_withdraw(user_id: int, is_admin: bool = False) -> tuple[bool, str]:
    """Returns (can_withdraw, reason_if_not)."""
    if is_admin:
        return True, "ok"

    from datetime import datetime, timezone, timedelta
    pool = await get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT balance, tasks_done, last_withdraw FROM users WHERE user_id=$1", user_id
        )
        if not user:
            return False, "not_found"
        if not user["tasks_done"]:
            return False, "tasks_incomplete"
        if float(user["balance"]) < MIN_WITHDRAW:
            return False, f"low_balance:{float(user['balance']):.2f}"
        if user["last_withdraw"]:
            cooldown_end = user["last_withdraw"] + timedelta(days=WITHDRAW_COOLDOWN_DAYS)
            if datetime.now(timezone.utc) < cooldown_end:
                remaining = cooldown_end - datetime.now(timezone.utc)
                days = remaining.days
                hours = remaining.seconds // 3600
                return False, f"cooldown:{days}d {hours}h"
        return True, "ok"


async def create_withdrawal(user_id: int, amount: float, method: str, destination: str) -> int:
    """Deducts balance and creates withdrawal record. Returns withdrawal ID."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "UPDATE users SET balance=balance-$2, last_withdraw=NOW() WHERE user_id=$1",
                user_id, amount
            )
            row = await conn.fetchrow(
                """INSERT INTO withdrawals (user_id, amount, method, destination)
                   VALUES ($1,$2,$3,$4) RETURNING id""",
                user_id, amount, method, destination
            )
            return row["id"]


async def get_pending_withdrawals() -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT w.*, u.full_name FROM withdrawals w
               JOIN users u ON w.user_id=u.user_id
               WHERE w.status='pending' ORDER BY w.requested_at ASC"""
        )


# ─────────────────────────────────────────────────────────────────────────────
# Promoted Groups
# ─────────────────────────────────────────────────────────────────────────────

async def upsert_group(chat_id: int, title: str, owner_id: int) -> asyncpg.Record:
    """Register or update a promoted group."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """
            INSERT INTO promoted_groups (chat_id, title, owner_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (chat_id) DO UPDATE
                SET title=$2, owner_id=$3
            RETURNING *
            """,
            chat_id, title, owner_id
        )


async def get_groups_by_owner(owner_id: int) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM promoted_groups WHERE owner_id=$1 ORDER BY chat_id",
            owner_id
        )


async def get_group(chat_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM promoted_groups WHERE chat_id=$1", chat_id
        )


async def update_group_interval(chat_id: int, interval_hours: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE promoted_groups SET interval_hours=$2 WHERE chat_id=$1",
            chat_id, interval_hours
        )


async def toggle_group(chat_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "UPDATE promoted_groups SET active=NOT active WHERE chat_id=$1 RETURNING *",
            chat_id
        )


async def delete_group(chat_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM promoted_groups WHERE chat_id=$1", chat_id
        )


async def get_groups_due_for_promotion() -> list[asyncpg.Record]:
    """Return all active groups where it's time to post again."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """
            SELECT pg.*, u.user_id AS u_id
            FROM promoted_groups pg
            JOIN users u ON pg.owner_id = u.user_id
            WHERE pg.active = TRUE
              AND pg.last_posted_at + (pg.interval_hours * INTERVAL '1 hour') <= NOW()
            """
        )


async def mark_group_posted(chat_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE promoted_groups SET last_posted_at=NOW() WHERE chat_id=$1",
            chat_id
        )


async def process_withdrawal(withdrawal_id: int, status: str, reject_reason: Optional[str] = None) -> Optional[asyncpg.Record]:
    """status: 'paid' or 'rejected'. Refunds balance on rejection."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            w = await conn.fetchrow("SELECT * FROM withdrawals WHERE id=$1", withdrawal_id)
            if not w:
                return None
            await conn.execute(
                "UPDATE withdrawals SET status=$2, processed_at=NOW(), reject_reason=$3 WHERE id=$1",
                withdrawal_id, status, reject_reason
            )
            if status == "rejected":
                await conn.execute(
                    "UPDATE users SET balance=balance+$2, last_withdraw=NULL WHERE user_id=$1",
                    w["user_id"], w["amount"]
                )
            return w


# ─────────────────────────────────────────────────────────────────────────────
# User Profiles
# ─────────────────────────────────────────────────────────────────────────────

async def get_profile(user_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            "SELECT * FROM user_profiles WHERE user_id=$1", user_id
        )


async def upsert_profile(user_id: int, **fields) -> None:
    """Save/update one or more profile fields. Pass field=value as kwargs."""
    if not fields:
        return
    pool = await get_pool()
    cols = list(fields.keys())
    vals = list(fields.values())
    # Build: INSERT ... ON CONFLICT DO UPDATE SET col=$2, ...
    set_clause = ", ".join(f"{c}=${i+2}" for i, c in enumerate(cols))
    async with pool.acquire() as conn:
        await conn.execute(
            f"""
            INSERT INTO user_profiles (user_id, {', '.join(cols)}, updated_at)
            VALUES ($1, {', '.join(f'${i+2}' for i in range(len(cols)))}, NOW())
            ON CONFLICT (user_id) DO UPDATE
              SET {set_clause}, updated_at=NOW()
            """,
            user_id, *vals
        )


# Map withdrawal method key → profile column name
_METHOD_FIELD = {
    "ton":    "ton_address",
    "usdt":   "usdt_address",
    "paypal": "paypal_email",
    "stars":  "stars_username",
}


async def get_saved_address(user_id: int, method: str) -> Optional[str]:
    """Return saved address/email for this withdrawal method, or None."""
    field = _METHOD_FIELD.get(method)
    if not field:
        return None
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {field} FROM user_profiles WHERE user_id=$1", user_id
        )
        if row:
            return row[field]
        return None


async def get_withdrawal_stats(user_id: int) -> dict:
    """Return the total paid and rejected withdrawal amounts for the user."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        paid = await conn.fetchval(
            "SELECT SUM(amount) FROM withdrawals WHERE user_id=$1 AND status='paid'",
            user_id
        )
        rejected = await conn.fetchval(
            "SELECT SUM(amount) FROM withdrawals WHERE user_id=$1 AND status='rejected'",
            user_id
        )
        return {
            "paid": float(paid) if paid else 0.0,
            "rejected": float(rejected) if rejected else 0.0
        }


# ─────────────────────────────────────────────────────────────────────────────
# Support Tickets
# ─────────────────────────────────────────────────────────────────────────────

async def create_ticket(user_id: int, message: str) -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "INSERT INTO tickets (user_id, message) VALUES ($1, $2) RETURNING id",
            user_id, message
        )


async def get_open_tickets(limit: int = 50) -> list[asyncpg.Record]:
    """Admin view: fetch latest unresolved tickets, sorted oldest first."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT t.*, u.full_name, u.username
               FROM tickets t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.status = 'open'
               ORDER BY t.created_at ASC
               LIMIT $1""",
            limit
        )


async def get_ticket(ticket_id: int) -> Optional[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchrow(
            """SELECT t.*, u.full_name, u.username
               FROM tickets t
               JOIN users u ON t.user_id = u.user_id
               WHERE t.id = $1""",
            ticket_id
        )


async def reply_ticket(ticket_id: int, reply_text: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """UPDATE tickets 
               SET reply = $1, status = 'answered', updated_at = NOW() 
               WHERE id = $2""",
            reply_text, ticket_id
        )


async def close_ticket(ticket_id: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tickets SET status = 'closed', updated_at = NOW() WHERE id = $1",
            ticket_id
        )


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup helper
# ─────────────────────────────────────────────────────────────────────────────

async def get_all_real_user_ids() -> list[int]:
    """Return all real (non-fake) user IDs for cleanup scanning."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT user_id FROM users WHERE user_id > 0")
        return [r["user_id"] for r in rows]


async def delete_user(user_id: int) -> None:
    """Hard-delete a user and all related data (cascades via FK)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id=$1", user_id)

# ─────────────────────────────────────────────────────────────────────────────
# Lucky Draw
# ─────────────────────────────────────────────────────────────────────────────

async def add_lucky_draw_entry(user_id: int, stars_paid: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO lucky_draw_entries (user_id, stars_paid) VALUES ($1, $2)",
            user_id, stars_paid
        )

async def has_user_entered_today(user_id: int) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM lucky_draw_entries WHERE user_id=$1 AND draw_date=CURRENT_DATE",
            user_id
        )
        return count > 0

async def get_today_lucky_draw_entries_count() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetchval("SELECT COUNT(*) FROM lucky_draw_entries WHERE draw_date=CURRENT_DATE")

async def get_today_lucky_draw_participants() -> list[int]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        records = await conn.fetch("SELECT DISTINCT user_id FROM lucky_draw_entries WHERE draw_date=CURRENT_DATE")
        return [r["user_id"] for r in records]

async def set_today_lucky_draw_winners(w1: int, w2: int, w3: int, p1: str, p2: str, p3: str) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO lucky_draw_winners (draw_date, winner_1_id, winner_2_id, winner_3_id, prize_1, prize_2, prize_3) 
               VALUES (CURRENT_DATE, $1, $2, $3, $4, $5, $6)
               ON CONFLICT (draw_date) DO UPDATE 
               SET winner_1_id=EXCLUDED.winner_1_id, 
                   winner_2_id=EXCLUDED.winner_2_id, 
                   winner_3_id=EXCLUDED.winner_3_id,
                   prize_1=EXCLUDED.prize_1,
                   prize_2=EXCLUDED.prize_2,
                   prize_3=EXCLUDED.prize_3""",
            w1, w2, w3, p1, p2, p3
        )

async def get_past_lucky_draw_winners(limit: int = 5) -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT 
                 w.draw_date, w.prize_1, w.prize_2, w.prize_3,
                 u1.full_name as w1_name, u1.username as w1_uname,
                 u2.full_name as w2_name, u2.username as w2_uname,
                 u3.full_name as w3_name, u3.username as w3_uname
               FROM lucky_draw_winners w
               JOIN users u1 ON w.winner_1_id = u1.user_id
               JOIN users u2 ON w.winner_2_id = u2.user_id
               JOIN users u3 ON w.winner_3_id = u3.user_id
               ORDER BY w.draw_date DESC LIMIT $1""",
            limit
        )


async def get_lucky_draw_admin_stats() -> dict:
    """Return aggregated Lucky Draw statistics for the admin panel."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        today_entries = await conn.fetchval(
            "SELECT COUNT(*) FROM lucky_draw_entries WHERE draw_date=CURRENT_DATE"
        )
        today_stars = await conn.fetchval(
            "SELECT COALESCE(SUM(stars_paid), 0) FROM lucky_draw_entries WHERE draw_date=CURRENT_DATE"
        )
        total_entries = await conn.fetchval("SELECT COUNT(*) FROM lucky_draw_entries")
        total_stars = await conn.fetchval(
            "SELECT COALESCE(SUM(stars_paid), 0) FROM lucky_draw_entries"
        )
        unique_buyers = await conn.fetchval(
            "SELECT COUNT(DISTINCT user_id) FROM lucky_draw_entries WHERE user_id > 0"
        )
        return {
            "today_entries": int(today_entries),
            "today_stars": int(today_stars),
            "total_entries": int(total_entries),
            "total_stars": int(total_stars),
            "unique_buyers": int(unique_buyers),
        }


async def get_lucky_draw_entry_history(limit: int = 20) -> list:
    """Return the last N real-user Lucky Draw purchases for the admin history log."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            """SELECT e.draw_date, e.stars_paid, e.created_at,
                      u.full_name, u.username, u.user_id
               FROM lucky_draw_entries e
               JOIN users u ON e.user_id = u.user_id
               WHERE u.user_id > 0
               ORDER BY e.created_at DESC
               LIMIT $1""",
            limit
        )

