"""
handlers/referral.py  ─  Share & Refer screens (both show the same referral link).

"Share" = quick share button focus
"Refer" = stats + leaderboard rank focus
Both display the same invite link.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, invite_link as build_invite, fmt_balance, BOT_NAME


async def nav_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _render_share(query)


async def nav_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await _render_refer(query)


async def _render_share(query):
    user_id = query.from_user.id
    link = build_invite(user_id)

    text = (
        f"📤 *Share & Earn*\n\n"
        f"🔗 Your invite link:\n"
        f"`{link}`\n\n"
        f"Share this link with friends.\n"
        f"When they join and complete all tasks, you earn *$0.40* automatically!\n\n"
        f"💡 *Tips:*\n"
        f"• Share in groups and channels\n"
        f"• Post on social media\n"
        f"• The more you share, the more you earn!"
    )

    share_text = (
        f"💰 Join {BOT_NAME} and earn money easily!\n\n"
        f"✦ Earn $0.40 per referral\n"
        f"✦ $0.50 free daily bonus\n"
        f"✦ Weekly prizes for top inviters\n\n"
        f"👉 {link}"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(
                "📤 Share Link",
                switch_inline_query=share_text
            )],
            [InlineKeyboardButton("👥 View Referral Stats", callback_data="nav:refer")],
            [InlineKeyboardButton("🏠 Home", callback_data="nav:start")],
        ]),
    )


async def _render_refer(query):
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    if not user:
        await query.answer("Please /start first.", show_alert=True)
        return

    link = build_invite(user_id)
    weekly_rank = await db.get_weekly_invite_rank(user_id)
    top = await db.get_leaderboard(3)

    text = (
        f"👥 *Referral Program*\n\n"
        f"🔗 Your invite link:\n"
        f"`{link}`\n\n"
        f"📊 *Your Stats:*\n"
        f"✅ Total Invites: *{user['total_invites']}*\n"
        f"💰 Balance: *{fmt_balance(user['balance'])}*\n"
        f"🏆 Weekly Rank: *#{weekly_rank}*\n\n"
        f"💡 Earn *$0.40* for every friend who joins and completes tasks.\n\n"
        f"🏆 *Weekly Prizes:*\n"
        f"🥇 1st–3rd: $10 each\n"
        f"🥈 4th–10th: $5 each\n"
        f"🥉 11th–20th: $3 each\n\n"
        f"🔥 *Top 3 This Week:*\n"
    )
    for i, u in enumerate(top, 1):
        medals = ["🥇", "🥈", "🥉"]
        name = (u["full_name"] or "User")[:20]
        text += f"{medals[i-1]} {name} — {u['total_invites']} invites\n"

    share_text = (
        f"💰 Join {BOT_NAME} and earn money easily!\n"
        f"👉 {link}"
    )

    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 Share Link", switch_inline_query=share_text)],
            [InlineKeyboardButton("🏆 Leaderboard", callback_data="earnings:leaderboard")],
            [InlineKeyboardButton("🏠 Home", callback_data="nav:start")],
        ]),
    )
