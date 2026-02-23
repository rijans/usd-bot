"""
handlers/earnings.py  ─  Earnings screen: balance, daily bonus, leaderboard.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import date

import core.db as db
from core.ui import nav_keyboard, fmt_balance, progress_bar

DAILY_AMOUNT = 0.50
MEDALS = ["🥇", "🥈", "🥉"]


async def nav_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    user = await db.get_user(user_id)
    if not user:
        await query.answer("Please /start first.", show_alert=True)
        return

    rank = await db.get_rank(user_id)
    weekly_rank = await db.get_weekly_invite_rank(user_id)

    # Daily bonus status
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
        buttons = [[InlineKeyboardButton("📋 Go to Tasks", callback_data="nav:tasks")]]
    else:
        if daily_available:
            text += f"🎁 Daily bonus available! Tap to claim *{fmt_balance(DAILY_AMOUNT)}*\n"
        else:
            text += f"🎁 Daily bonus: claimed ✅ — come back tomorrow!\n"

        text += "\n🏆 *Weekly Top 5 Inviters:*\n"
        top = await db.get_leaderboard(5)
        for i, u in enumerate(top, 1):
            medal = MEDALS[i - 1] if i <= 3 else f"{i}."
            name = (u["full_name"] or "User")[:20]
            text += f"{medal} {name} — *{u['total_invites']} invites*\n"

        buttons = []
        if daily_available:
            buttons.append([InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data="earnings:daily")])
        buttons.append([InlineKeyboardButton("🏆 Full Leaderboard", callback_data="earnings:leaderboard")])

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons + [[
            InlineKeyboardButton("🏠 Home", callback_data="nav:start")
        ]]),
    )


async def claim_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    success, reason = await db.claim_daily_bonus(user_id, DAILY_AMOUNT)
    user = await db.get_user(user_id)

    if success:
        text = (
            f"🎁 *Daily Bonus Claimed!*\n\n"
            f"✅ You received *{fmt_balance(DAILY_AMOUNT)}*!\n\n"
            f"💵 New Balance: *{fmt_balance(user['balance'])}*\n\n"
            f"Come back tomorrow for your next bonus 🔄"
        )
    elif reason == "already_claimed":
        text = (
            f"⏰ *Already Claimed Today*\n\n"
            f"You already claimed your bonus today.\n\n"
            f"💵 Balance: *{fmt_balance(user['balance'])}*\n\n"
            f"Come back tomorrow for *{fmt_balance(DAILY_AMOUNT)}* 🔄"
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

    top = await db.get_leaderboard(20)
    weekly_rank = await db.get_weekly_invite_rank(user_id)
    user = await db.get_user(user_id)

    text = "🏆 *Weekly Top Inviters*\n\n"
    for i, u in enumerate(top, 1):
        medal = MEDALS[i - 1] if i <= 3 else f"{i}."
        prize = {1: "$10", 2: "$10", 3: "$10"}.get(i, "$5" if i <= 10 else "$3")
        name = (u["full_name"] or "User")[:20]
        text += f"{medal} {name} — *{u['total_invites']} inv* ({prize})\n"

    text += (
        f"\n📊 *Your Position:* #{weekly_rank}\n"
        f"👥 Your Invites: *{user['total_invites'] if user else 0}*\n\n"
        f"🏆 *Prizes:*\n"
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
