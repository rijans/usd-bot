from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import date

import core.db as db
from core.ui import nav_keyboard, fmt_balance

MEDALS = ["🥇", "🥈", "🥉"]


async def nav_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles both callback (inline button) and message (reply keyboard)."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        send_fn = query.edit_message_text
    else:
        user_id = update.effective_user.id
        send_fn = None

    user = await db.get_user(user_id)
    if not user:
        if update.callback_query:
            await update.callback_query.answer("Please /start first.", show_alert=True)
        return

    rank         = await db.get_rank(user_id)
    weekly_rank  = await db.get_weekly_invite_rank(user_id)
    daily_reward = await db.get_setting("daily_reward")
    daily_available = (not user["last_daily"]) or (user["last_daily"] < date.today())

    text = (
        f"💰 *Earnings*\n\n"
        f"💵 Balance: *{fmt_balance(user['balance'])}*\n"
        f"📊 Overall Rank: *#{rank}*\n"
        f"🏆 Weekly Invite Rank: *#{weekly_rank}*\n"
        f"👥 Total Invites: *{user['total_invites']}*\n\n"
    )

    if not user["tasks_done"]:
        text += "⚠️ Complete all tasks to start earning!\n"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Go to Tasks", callback_data="nav:tasks")],
            [InlineKeyboardButton("🏠 Home",        callback_data="nav:start")],
        ])
    else:
        if daily_available:
            text += f"🎁 Daily bonus *${daily_reward}* is available! Claim it now.\n\n"
        else:
            text += f"🎁 Daily bonus: claimed ✅ — come back tomorrow!\n\n"

        text += "🏆 *Top 5 Inviters This Week:*\n"
        top = await db.get_leaderboard(5)
        for i, u in enumerate(top, 1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}."
            name  = (u["full_name"] or "User")[:18]
            text += f"{medal} {name} — *{u['total_invites']} invites*\n"

        buttons = []
        if daily_available:
            buttons.append([InlineKeyboardButton(f"🎁 Claim ${daily_reward} Daily Bonus", callback_data="earnings:daily")])
        buttons.append([InlineKeyboardButton("🏆 Full Leaderboard", callback_data="earnings:leaderboard")])
        buttons.append([InlineKeyboardButton("🏠 Home",             callback_data="nav:start")])
        keyboard = InlineKeyboardMarkup(buttons)

    if send_fn:
        await send_fn(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    success, result = await db.claim_daily_bonus(user_id)
    user = await db.get_user(user_id)

    if success:
        amount = result
        text = (
            f"🎁 *Daily Bonus Claimed!*\n\n"
            f"✅ You received *${amount:.2f}*!\n\n"
            f"💵 New Balance: *{fmt_balance(user['balance'])}*\n\n"
            f"Come back tomorrow for your next bonus 🔄"
        )
    elif result == "already_claimed":
        daily_reward = await db.get_setting("daily_reward")
        text = (
            f"⏰ *Already Claimed Today*\n\n"
            f"You already claimed your bonus today.\n\n"
            f"💵 Balance: *{fmt_balance(user['balance'])}*\n\n"
            f"Come back tomorrow for *${daily_reward}* 🔄"
        )
    else:
        text = "⚠️ Complete all tasks first to claim daily bonuses."

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to Earnings", callback_data="nav:earnings")]
        ]),
    )


async def show_leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    top         = await db.get_leaderboard(20)
    weekly_rank = await db.get_weekly_invite_rank(user_id)
    user        = await db.get_user(user_id)

    text = "🏆 *Weekly Top Inviters*\n\n"
    for i, u in enumerate(top, 1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}."
        prize = "$10" if i <= 3 else ("$5" if i <= 10 else "$3")
        name  = (u["full_name"] or "User")[:18]
        text += f"{medal} {name} — *{u['total_invites']} inv* ({prize})\n"

    text += (
        f"\n📊 *Your Position:* #{weekly_rank}\n"
        f"👥 Your Invites: *{user['total_invites'] if user else 0}*\n\n"
        f"🏆 *Prize Structure:*\n"
        f"🥇 1st–3rd: $10 each\n"
        f"🥈 4th–10th: $5 each\n"
        f"🥉 11th–20th: $3 each"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back to Earnings", callback_data="nav:earnings")]
        ]),
    )