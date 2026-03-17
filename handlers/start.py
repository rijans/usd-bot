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
        [KeyboardButton("💰 Earnings"),       KeyboardButton("📋 Tasks")],
        [KeyboardButton("🤝 Refer & Earn"),   KeyboardButton("❓ FAQ")],
        [KeyboardButton("💸 Withdraw"),       KeyboardButton("🏠 Home")],
    ],
    resize_keyboard=True,
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

    record, is_new, signup_amt = await db.upsert_user(
        user_id=user.id,
        username=user.username or "",
        full_name=user.full_name,
        referred_by=referred_by,
    )

    if is_new and signup_amt > 0:
        try:
            await update.message.reply_text(
                f"🎉 *Welcome Bonus!* You received *{fmt_balance(signup_amt)}* just for joining!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    await _send_home(update, record, is_new=is_new)


async def nav_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called by the 🏠 Home inline button OR the 🏠 Home reply keyboard button."""
    # Handle both inline callback and reply keyboard text
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        record = await db.get_user(query.from_user.id)
        if not record:
            record, _, _ = await db.upsert_user(
                query.from_user.id, query.from_user.username or "", query.from_user.full_name
            )
        await _edit_home(query, record)
    else:
        # Triggered by reply keyboard "🏠 Home" button
        record = await db.get_user(update.effective_user.id)
        if not record:
            record, _, _ = await db.upsert_user(
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
        daily_primary = await db.get_setting("daily_bonus_primary", "0.20")
        ref_primary = await db.get_setting("referral_reward_primary", "0.30")
        signup_amount = await db.get_setting("signup_bonus", "1.00")
        task_amount = await db.get_setting("task_reward", "0.30")
        ref_threshold = await db.get_setting("referral_reward_threshold", "5")
        
        text += (
            f"💰 Balance: *{fmt_balance(record['balance'])}*\n"
            f"👥 Total Invites: *{record['total_invites']}*\n\n"
            f"📖 *How to earn:*\n"
            f"• 🎉 {fmt_balance(signup_amount)} welcome bonus (instant!)\n"
            f"• 📋 {fmt_balance(task_amount)} per task completed\n"
            f"• 👥 Up to {fmt_balance(ref_primary)} per referral (first {ref_threshold} pay more!)\n"
            f"• 🎁 Up to {fmt_balance(daily_primary)} daily bonus\n"
            f"• 🏆 Climb the leaderboard for weekly prizes\n\n"
            f"🚀 *Invite friends to earn faster — the more you refer, the closer you get to $20(minimum withdraw amount)!*\n\n"
            f"💸 *Withdraw via:* TON · USDT · Telegram Stars · PayPal"
        )

    # Send both the reply keyboard (persistent bottom bar) and the inline
    # nav keyboard attached to the same big message — wide text = wide buttons!
    await update.message.reply_text(
        text,
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
        daily_primary = await db.get_setting("daily_bonus_primary", "0.20")
        ref_primary = await db.get_setting("referral_reward_primary", "0.30")
        signup_amount = await db.get_setting("signup_bonus", "1.00")
        task_amount = await db.get_setting("task_reward", "0.30")
        ref_threshold = await db.get_setting("referral_reward_threshold", "5")
        
        text += (
            f"💰 Balance: *{fmt_balance(record['balance'])}*\n"
            f"👥 Total Invites: *{record['total_invites']}*\n\n"
            f"📖 *How to earn:*\n"
            f"• 🎉 {fmt_balance(signup_amount)} welcome bonus\n"
            f"• 📋 {fmt_balance(task_amount)} per task completed\n"
            f"• 👥 Up to {fmt_balance(ref_primary)} per referral (first {ref_threshold} pay more!)\n"
            f"• 🎁 Up to {fmt_balance(daily_primary)} daily bonus\n"
            f"• 🏆 Weekly leaderboard prizes\n\n"
            f"🚀 *Invite more friends to earn faster!*\n\n"
            f"💸 *Withdraw via:* TON · USDT · Telegram Stars · PayPal"
        )

    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
    except BadRequest as e:
        if "Message is not modified" not in str(e):
            raise