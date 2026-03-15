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
    await _render_refer(update, context)

async def nav_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _render_refer(update, context)


async def _render_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    if query:
        await query.answer()
        
    user = await db.get_user(user_id)
    if not user:
        msg = "Please /start first."
        if query: await query.answer(msg, show_alert=True)
        else: await update.message.reply_text(msg)
        return

    link = build_invite(user_id)
    weekly_rank = await db.get_weekly_invite_rank(user_id)
    top = await db.get_leaderboard(3)

    text = (
        f"👥 *Refer & Earn*\n\n"
        f"🔗 Your invite link:\n"
        f"`{link}`\n\n"
        f"💡 Share this link with friends! When they join and complete all tasks, you earn *$0.40* automatically.\n\n"
        f"📊 *Your Stats:*\n"
        f"✅ Total Invites: *{user['total_invites']}*\n"
        f"💰 Balance: *{fmt_balance(user['balance'])}*\n"
        f"🏆 Weekly Rank: *#{weekly_rank}*\n\n"
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

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Link", switch_inline_query=share_text)],
        [InlineKeyboardButton("🏆 Leaderboard", callback_data="earnings:leaderboard")],
        [InlineKeyboardButton("🏠 Home", callback_data="nav:start")],
    ])

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
