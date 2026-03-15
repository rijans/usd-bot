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
"""

async def init_schema():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(SCHEMA)
        
        # Add reject_reason column for backward compatibility
        await conn.execute("ALTER TABLE withdrawals ADD COLUMN IF NOT EXISTS reject_reason TEXT;")
        
        # Insert defaults if empty
        await conn.execute(
            """INSERT INTO settings (key, value)
               VALUES ('daily_bonus', '0.50'),
                      ('referral_reward', '0.40'),
                      ('signup_bonus', '1.00'),
                      ('task_reward', '0.50')
               ON CONFLICT (key) DO NOTHING"""
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
        row = await conn.fetchrow(
            "SELECT COUNT(*)+1 AS rank FROM users WHERE total_invites > "
            "(SELECT total_invites FROM users WHERE user_id=$1)",
            user_id
        )
        return row["rank"]


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
    """Returns (success, reason, amount_credited)"""
    from datetime import date
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT last_daily, tasks_done FROM users WHERE user_id=$1", user_id)
        if not row or not row["tasks_done"]:
            return False, "tasks_incomplete", 0.0
        today = date.today()
        if row["last_daily"] and row["last_daily"] >= today:
            return False, "already_claimed", 0.0
            
        amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='daily_bonus'")
        amount = float(amt_str) if amt_str else 0.50
        
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
        rows = await conn.fetch("SELECT user_id FROM users WHERE banned=FALSE")
        return [r["user_id"] for r in rows]


async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM users")
        active = await conn.fetchval("SELECT COUNT(*) FROM users WHERE tasks_done=TRUE")
        total_paid = await conn.fetchval("SELECT COALESCE(SUM(balance),0) FROM users")
        p_w = await conn.fetchval("SELECT COUNT(*) FROM withdrawals WHERE status='pending'")
        return {
            "total_users": total,
            "active_users": active,
            "total_balance_owed": float(total_paid),
            "pending_withdrawals": p_w,
        }


async def get_leaderboard(limit: int = 20) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, full_name, total_invites, balance "
            "FROM users ORDER BY total_invites DESC LIMIT $1",
            limit
        )

async def get_earners_leaderboard(limit: int = 10) -> list[asyncpg.Record]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT user_id, full_name, total_invites, balance "
            "FROM users ORDER BY balance DESC LIMIT $1",
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
                ref = await conn.fetchrow("SELECT tasks_done FROM users WHERE user_id=$1", referrer_id)
                if ref:
                    amt_str = await conn.fetchval("SELECT value FROM settings WHERE key='referral_reward'")
                    ref_amt = float(amt_str) if amt_str else 0.40
                    
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
