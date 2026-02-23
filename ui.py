"""
core/ui.py  ─  Shared keyboards, text helpers, membership verification.
"""
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
import asyncpg

BOT_USERNAME = os.environ.get("BOT_USERNAME", "Dollar_Earning_Crypto_Bot")
BOT_NAME     = os.environ.get("BOT_NAME",     "Dollar Earning Crypto Bot")


# ─────────────────────────────────────────────────────────────────────────────
# Main navigation keyboard (bottom of most screens)
# ─────────────────────────────────────────────────────────────────────────────

def nav_keyboard(extra: list[list[InlineKeyboardButton]] = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("🏠 Start",     callback_data="nav:start"),
            InlineKeyboardButton("📋 Tasks",     callback_data="nav:tasks"),
        ],
        [
            InlineKeyboardButton("📤 Share",     callback_data="nav:share"),
            InlineKeyboardButton("💰 Earnings",  callback_data="nav:earnings"),
        ],
        [
            InlineKeyboardButton("👥 Refer",     callback_data="nav:refer"),
            InlineKeyboardButton("💸 Withdraw",  callback_data="nav:withdraw"),
        ],
    ]
    if extra:
        rows = extra + rows
    return InlineKeyboardMarkup(rows)


def back_keyboard(target: str = "nav:start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=target)]])


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────

def user_display(record) -> str:
    name = record["full_name"] or f"User {record['user_id']}"
    return name


def invite_link(user_id: int) -> str:
    return f"https://t.me/{BOT_USERNAME}?start={user_id}"


def fmt_balance(amount) -> str:
    return f"${float(amount):.2f}"


def progress_bar(done: int, total: int, width: int = 8) -> str:
    filled = round(width * done / total) if total else 0
    return "▓" * filled + "░" * (width - filled)


# ─────────────────────────────────────────────────────────────────────────────
# Membership check
# ─────────────────────────────────────────────────────────────────────────────

async def is_member(bot, user_id: int, chat_id: str) -> bool:
    """
    Returns True if user is a member of chat_id.
    chat_id can be @username or a numeric -100xxx id.
    """
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status not in ("left", "kicked", "banned")
    except (BadRequest, Forbidden):
        return False


async def check_all_tasks(bot, user_id: int, tasks: list) -> dict[int, bool]:
    """
    Returns {task_id: True/False} for each task.
    Uses asyncio.gather for parallel membership checks.
    """
    import asyncio
    results = await asyncio.gather(
        *[is_member(bot, user_id, t["chat_id"]) for t in tasks],
        return_exceptions=True
    )
    return {
        t["id"]: (r if isinstance(r, bool) else False)
        for t, r in zip(tasks, results)
    }
