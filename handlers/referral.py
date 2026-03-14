from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, invite_link as build_invite, fmt_balance, BOT_NAME


async def nav_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles both callback (inline button) and message (reply keyboard)."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        edit_fn = query.edit_message_text
    else:
        user_id = update.effective_user.id
        edit_fn = None

    user = await db.get_user(user_id)
    if not user:
        if update.callback_query:
            await update.callback_query.answer("Please /start first.", show_alert=True)
        return

    link        = build_invite(user_id)
    weekly_rank = await db.get_weekly_invite_rank(user_id)
    top         = await db.get_leaderboard(3)
    ref_reward  = await db.get_setting("referral_reward")

    medals = ["🥇", "🥈", "🥉"]
    text = (
        f"🎯 *Refer & Earn*\n\n"
        f"🔗 Your invite link:\n"
        f"`{link}`\n\n"
        f"📊 *Your Stats:*\n"
        f"✅ Total Invites: *{user['total_invites']}*\n"
        f"💰 Balance: *{fmt_balance(user['balance'])}*\n"
        f"🏆 Weekly Rank: *#{weekly_rank}*\n\n"
        f"💡 Earn *${ref_reward}* for every friend who joins and completes all tasks.\n\n"
        f"🏆 *Weekly Prizes:*\n"
        f"🥇 1st–3rd place: $10 each\n"
        f"🥈 4th–10th place: $5 each\n"
        f"🥉 11th–20th place: $3 each\n\n"
        f"🔥 *Top 3 This Week:*\n"
    )
    for i, u in enumerate(top, 1):
        name = (u["full_name"] or "User")[:20]
        text += f"{medals[i-1]} {name} — {u['total_invites']} invites\n"

    share_text = (
        f"💰 Join {BOT_NAME} and earn money easily!\n"
        f"✦ Earn ${ref_reward} per referral\n"
        f"✦ Free daily bonus\n"
        f"✦ Weekly prizes for top inviters\n\n"
        f"👉 {link}"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share Your Link", switch_inline_query=share_text)],
        [InlineKeyboardButton("🏆 Full Leaderboard", callback_data="earnings:leaderboard")],
        [InlineKeyboardButton("🏠 Home",             callback_data="nav:start")],
    ])

    if edit_fn:
        await edit_fn(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# Keep nav_share as an alias — routes to the same place
nav_share = nav_refer