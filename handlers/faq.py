"""
handlers/faq.py  ─  FAQ page for users.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import fmt_balance


FAQ_SECTIONS = [
    ("faq:earning",   "💰 How do I earn?"),
    ("faq:daily",     "🎁 Daily Bonus"),
    ("faq:refer",     "🤝 Referrals & Invites"),
    ("faq:withdraw",  "💸 Withdrawals"),
    ("faq:leaderboard", "🏆 Leaderboard & Prizes"),
    ("faq:groups",    "📢 Group Auto-Promoter"),
]

FAQ_CONTENT = {
    "faq:earning": (
        "💰 *How Do I Earn?*\n\n"
        "There are 4 ways to earn:\n\n"
        "1️⃣ *Welcome Bonus* — You get a bonus automatically when you first start the bot. No action needed!\n\n"
        "2️⃣ *Task Rewards* — Go to 📋 Tasks and join each listed channel. After joining, tap 'I Joined' to verify and earn your reward.\n\n"
        "3️⃣ *Referral Rewards* — Share your referral link with friends. You earn every time a friend joins and completes all tasks.\n\n"
        "4️⃣ *Daily Bonus* — Come back every day and claim your daily bonus from 💰 Earnings. "
        "*You must invite at least 2 new users each week to keep the daily bonus active.*"
    ),
    "faq:daily": (
        "🎁 *Daily Bonus — How It Works*\n\n"
        "• Open 💰 Earnings every day and tap *Claim Daily Bonus*\n"
        "• The bonus is tiered — your first few days earn a higher amount, then it decreases slightly\n\n"
        "⚠️ *Weekly Invite Requirement*\n"
        "To claim the daily bonus, you must have invited *at least 2 new users in the current week*.\n"
        "If you haven't, the bot will show your current progress (e.g. \"1/2 invites this week\") "
        "and ask you to invite more friends.\n\n"
        "📅 *The week resets every Monday.*\n\n"
        "🔔 *Reminder*: The bot will automatically send you a daily reminder if you haven't claimed your bonus yet."
    ),
    "faq:refer": (
        "🤝 *Referrals & Invites*\n\n"
        "*How to share your referral link:*\n"
        "Tap *🤝 Refer & Earn* in the menu to see your personal invite link.\n\n"
        "*How referral rewards work:*\n"
        "• Your friend must join via your link and complete *all tasks*\n"
        "• Once they complete tasks, you automatically earn a referral reward\n"
        "• The reward is tiered — your first several referrals earn more, then a lower rate applies\n\n"
        "*Why the task requirement?*\n"
        "This prevents fake accounts and ensures every referral is a genuine active user.\n\n"
        "*Weekly invite requirement for daily bonus:*\n"
        "You need to invite at least *2 real users per week* to keep your daily bonus unlocked."
    ),
    "faq:withdraw": (
        "💸 *Withdrawals — How It Works*\n\n"
        "*Minimum withdrawal:* $20.00\n\n"
        "*Supported methods:*\n"
        "• TON (Crypto)\n"
        "• USDT (Crypto)\n"
        "• Telegram Stars\n"
        "• PayPal\n\n"
        "*Steps to withdraw:*\n"
        "1. Tap *💸 Withdraw* in the menu\n"
        "2. Choose your preferred payment method\n"
        "3. Enter your wallet address / email / username\n"
        "4. Your request is submitted for admin review\n"
        "5. Once approved, payment is sent. If rejected, your balance is refunded automatically.\n\n"
        "⏳ *Processing time:* Withdrawals are reviewed manually and usually processed within 24–72 hours.\n\n"
        "🔒 *15-day cooldown:* After each withdrawal, you must wait 15 days before submitting another request."
    ),
    "faq:leaderboard": (
        "🏆 *Leaderboard & Weekly Prizes*\n\n"
        "The leaderboard ranks users by how many people they've invited in the current week.\n\n"
        "*Weekly Prize Pool:*\n"
        "🥇 1st–3rd place: $10 each\n"
        "🥈 4th–10th place: $5 each\n"
        "🥉 11th–20th place: $3 each\n\n"
        "Prizes are added directly to your balance at the end of each week.\n\n"
        "*How to climb the leaderboard:*\n"
        "• Share your referral link in groups, social media, and with friends\n"
        "• Every verified invite counts toward your weekly rank\n\n"
        "📊 You can see your current rank in 💰 Earnings."
    ),
    "faq:groups": (
        "📢 *Group Auto-Promoter*\n\n"
        "If you own or admin a Telegram group, you can use the bot to automatically post your referral link there!\n\n"
        "*How to set it up:*\n"
        "1️⃣ Add this bot to your group\n"
        "2️⃣ Make the bot an *Administrator* (so it has permission to send messages)\n"
        "3️⃣ The bot will send you a private message confirming it's registered\n"
        "4️⃣ Tap *👥 For Group Owners* in this bot's menu\n"
        "5️⃣ Select your group and configure:\n"
        "   • *Interval:* How often to post (1h / 3h / 6h / 12h / 24h)\n"
        "   • *Toggle:* Pause or resume auto-posting anytime\n\n"
        "Every auto-post contains your personal referral link, driving new signups for you automatically! 🚀"
    ),
}


def _faq_menu_keyboard() -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(label, callback_data=cb)] for cb, label in FAQ_SECTIONS]
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="nav:start")])
    return InlineKeyboardMarkup(buttons)


def _faq_back_keyboard(section_cb: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Back to FAQ", callback_data="nav:faq")],
        [InlineKeyboardButton("🏠 Home", callback_data="nav:start")],
    ])


async def nav_faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main FAQ menu."""
    text = (
        "❓ *Frequently Asked Questions*\n\n"
        "Choose a topic below to learn more:"
    )
    markup = _faq_menu_keyboard()

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def faq_section(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a specific FAQ section."""
    query = update.callback_query
    await query.answer()
    section = query.data  # e.g. "faq:earning"

    content = FAQ_CONTENT.get(section)
    if not content:
        await query.answer("Section not found.", show_alert=True)
        return

    await query.edit_message_text(
        content,
        parse_mode="Markdown",
        reply_markup=_faq_back_keyboard(section),
    )
