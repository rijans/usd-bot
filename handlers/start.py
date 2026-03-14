from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.error import BadRequest
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, BOT_NAME, fmt_balance


REPLY_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💰 Earnings"),    KeyboardButton("📋 Tasks")],
        [KeyboardButton("💸 Withdraw"),    KeyboardButton("🎯 Refer & Earn")],
        [KeyboardButton("🏠 Home")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Choose an option...",
)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = None
    if context.args:
        try:
            ref_id = int(context.args[0])
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
        referral_reward = await db.get_setting("referral_reward")
        daily_reward    = await db.get_setting("daily_reward")
        text += (
            f"💰 Balance: *{fmt_balance(record['balance'])}*\n"
            f"👥 Total Invites: *{record['total_invites']}*\n\n"
            f"📖 *How to earn:*\n"
            f"• Earn *${referral_reward}* per referral (after they finish tasks)\n"
            f"• Claim *${daily_reward}* daily bonus for free\n"
            f"• Climb the leaderboard for weekly prizes\n\n"
            f"💸 *Withdraw via:* TON · PayPal · Mobile · PUBG UC"
        )

    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=REPLY_KEYBOARD
    )
    await update.message.reply_text(
        "👇 *Navigation:*", parse_mode="Markdown", reply_markup=nav_keyboard()
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
            f"Tap a button below to navigate."
        )

    try:
        await query.edit_message_text(
            text, parse_mode="Markdown", reply_markup=nav_keyboard()
        )
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise