"""
core/ui.py  ─  Shared keyboards, text helpers, membership verification.
"""
import os
import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Forbidden
import asyncpg

log = logging.getLogger(__name__)

BOT_USERNAME = os.environ.get("BOT_USERNAME", "Dollar_Earning_Crypto_Bot")
BOT_NAME     = os.environ.get("BOT_NAME",     "Dollar Earning Crypto Bot")


# ─────────────────────────────────────────────────────────────────────────────
# Main navigation keyboard (bottom of most screens)
# ─────────────────────────────────────────────────────────────────────────────

def nav_keyboard(extra: list[list[InlineKeyboardButton]] = None) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton("📋 Tasks",         callback_data="nav:tasks"),
            InlineKeyboardButton("🤝 Refer & Earn", callback_data="nav:refer"),
        ],
        [
            InlineKeyboardButton("💰 Earnings",      callback_data="nav:earnings"),
            InlineKeyboardButton("💸 Withdraw",      callback_data="nav:withdraw"),
        ],
        [
            InlineKeyboardButton("👤 Profile",      callback_data="nav:profile"),
            InlineKeyboardButton("❓ FAQ & Support",  callback_data="nav:faq"),
        ],
        [
            InlineKeyboardButton("👥 For Group Owners", callback_data="nav:groups"),
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
    except (BadRequest, Forbidden) as e:
        log.warning(f"Failed to check membership for {user_id} in {chat_id}: {e}. Granting access.")
        return True


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
