"""
handlers/start.py  ─  /start command and Home screen.

Flow:
  1. Parse optional referral: /start <user_id>
  2. Upsert user in DB
  3. Render home screen (tasks status + nav)
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, BOT_NAME, invite_link, fmt_balance


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

    # Parse referral
    referred_by = None
    if args:
        try:
            ref_id = int(args[0])
            if ref_id != user.id:
                referred_by = ref_id
        except ValueError:
            pass

    record, is_new = await db.upsert_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        referred_by=referred_by,
    )

    await _send_home(update, context, record, is_new=is_new)


async def nav_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called by the 🏠 Start nav button."""
    query = update.callback_query
    await query.answer()
    record = await db.get_user(query.from_user.id)
    if not record:
        record, _ = await db.upsert_user(
            query.from_user.id, query.from_user.username or "", query.from_user.full_name
        )
    await _edit_home(query, record)


async def _send_home(update: Update, context: ContextTypes.DEFAULT_TYPE, record, is_new=False):
    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(record["user_id"])
    done = len(completed_ids)
    total = len(tasks)
    tasks_done = record["tasks_done"]

    greeting = "👋 Welcome back" if not is_new else "🎉 Welcome"
    text = (
        f"{greeting}, *{record['full_name']}*!\n\n"
        f"✦ *{BOT_NAME}*\n"
        f"The generous earning bot on Telegram 🤑\n\n"
    )

    if not tasks_done:
        text += (
            f"⚠️ *Complete all tasks to unlock the bot!*\n"
            f"Progress: {done}/{total} tasks done\n\n"
            f"👉 Tap *Tasks* below to get started."
        )
    else:
        text += (
            f"💰 Balance: *{fmt_balance(record['balance'])}*\n"
            f"👥 Total Invites: *{record['total_invites']}*\n\n"
            f"📖 *How to earn:*\n"
            f"• Earn $0.40 per referral (after they finish tasks)\n"
            f"• Claim $0.50 daily bonus for free\n"
            f"• Climb the leaderboard for weekly prizes\n\n"
            f"💸 *Withdraw via:* TON · PayPal · Mobile · PUBG UC"
        )

    msg = update.message or (update.callback_query.message if update.callback_query else None)
    if msg:
        await msg.reply_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())


async def _edit_home(query, record):
    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(record["user_id"])
    done = len(completed_ids)
    total = len(tasks)
    tasks_done = record["tasks_done"]

    text = f"🏠 *{BOT_NAME}*\n\n"

    if not tasks_done:
        text += (
            f"⚠️ *Complete all tasks to unlock features!*\n"
            f"Progress: {done}/{total} tasks done\n\n"
            f"👉 Tap *Tasks* to continue."
        )
    else:
        text += (
            f"💰 Balance: *{fmt_balance(record['balance'])}*\n"
            f"👥 Total Invites: *{record['total_invites']}*\n\n"
            f"📖 *How to earn:*\n"
            f"• $0.40 per referral (after they finish tasks)\n"
            f"• $0.50 daily bonus\n"
            f"• Weekly leaderboard prizes"
        )

    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
