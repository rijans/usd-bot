"""
handlers/start.py  -  /start command and Home screen.
"""
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, BOT_NAME, fmt_balance


# Persistent bottom keyboard - always visible below the chat input
# This is what users see pinned at the bottom like in the screenshot
REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💰 Earnings"),   KeyboardButton("📋 Tasks")],
        [KeyboardButton("📤 Share"),      KeyboardButton("👥 Refer")],
        [KeyboardButton("💸 Withdraw"),   KeyboardButton("🏠 Home")],
    ],
    resize_keyboard=True,      # Makes buttons smaller, fits better on screen
#    persistent=True,           # Stays visible even after user sends a message
    input_field_placeholder="Choose an option or type a command...",
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args

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

    await _send_home(update, record, is_new=is_new)


async def nav_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called by the 🏠 Home inline button OR the 🏠 Home reply keyboard button."""
    # Handle both inline callback and reply keyboard text
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        record = await db.get_user(query.from_user.id)
        if not record:
            record, _ = await db.upsert_user(
                query.from_user.id, query.from_user.username or "", query.from_user.full_name
            )
        await _edit_home(query, record)
    else:
        # Triggered by reply keyboard "🏠 Home" button
        record = await db.get_user(update.effective_user.id)
        if not record:
            record, _ = await db.upsert_user(
                update.effective_user.id,
                update.effective_user.username or "",
                update.effective_user.full_name,
                )
        await _send_home(update, record)


async def _send_home(update: Update, record, is_new=False):
    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(record["user_id"])
    done = len(completed_ids)
    total = len(tasks)

    greeting = "🎉 Welcome" if is_new else "👋 Welcome back"
    text = (
        f"{greeting}, *{record['full_name']}*!\n\n"
        f"✦ *{BOT_NAME}*\n"
        f"The generous earning bot on Telegram\n\n"
    )

    if not record["tasks_done"]:
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

    # Send with BOTH the inline nav keyboard (on the message) AND
    # the persistent reply keyboard (pinned at bottom of screen)
    await update.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=REPLY_KEYBOARD,   # Sets the persistent bottom keyboard
    )
    # Then send the inline nav as a second message
    await update.message.reply_text(
        "👇 *Quick Navigation:*",
        parse_mode="Markdown",
        reply_markup=nav_keyboard(),
    )


async def _edit_home(query, record):
    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(record["user_id"])
    done = len(completed_ids)
    total = len(tasks)

    text = f"🏠 *{BOT_NAME}*\n\n"

    if not record["tasks_done"]:
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

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise