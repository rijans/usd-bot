"""
handlers/profile.py  ─  User Profile page.

Allows users to view and edit their personal + payment details.
Phone number can be shared via Telegram's native contact API or typed manually.
"""
import asyncio
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove,
)
from telegram.ext import ContextTypes, ConversationHandler

import core.db as db
from core.ui import fmt_balance, BOT_USERNAME, clean_md

# ConversationHandler state
EDIT_PROFILE_VALUE = 50   # Waiting for user to type a new value
AWAIT_PHONE_SHARE  = 51   # Waiting for Telegram contact share or manual text


# ── Field registry ────────────────────────────────────────────────────────────
# Ordered list of (db_column, emoji, display_label, placeholder)
PROFILE_FIELDS = [
    ("email",          "📧", "Email",                "e.g. you@example.com"),
    ("phone",          "📞", "Phone Number",          "e.g. +8801XXXXXXXXX"),
    ("ton_address",    "🔷", "TON Wallet",            "EQ…"),
    ("usdt_address",   "💵", "USDT Wallet",           "TU…"),
    ("paypal_email",   "💳", "PayPal Email",          "e.g. you@paypal.com"),
    ("stars_username", "⭐", "Stars Username",         "e.g. @yourname"),
    ("bio",            "💼", "Bio / Note",            "Short note about yourself"),
    ("alt_username",   "🔗", "Alt Telegram Account", "e.g. @otheraccount"),
    ("country",        "🌍", "Country",               "Select from list"),
]

FIELD_BY_KEY = {f[0]: f for f in PROFILE_FIELDS}


def _mask(value: str) -> str:
    """Show only the first 4 and last 4 chars for privacy."""
    if not value:
        return "—"
    if len(value) <= 8:
        return value
    return value[:4] + "…" + value[-4:]


def _profile_text(user, profile, w_stats=None) -> str:
    joined = user["joined_at"].strftime("%b %Y") if user.get("joined_at") else "?"
    name   = clean_md(user.get("full_name", "?"))
    uname  = clean_md(f"@{user['username']}") if user.get("username") else "—"
    
    paid = w_stats["paid"] if w_stats else 0.0
    rejected = w_stats["rejected"] if w_stats else 0.0

    lines = [
        f"👤 *Your Profile*\n",
        f"📛 *Name:* {name}",
        f"🆔 *Username:* {uname}",
        f"📅 *Member since:* {joined}",
        f"💰 *Balance:* {fmt_balance(user['balance'])}",
        f"✅ *Paid Withdrawals:* {fmt_balance(paid)}",
        f"❌ *Rejected Withdrawals:* {fmt_balance(rejected)}",
        f"\n━━━━━━━━━━━━━━\n",
    ]

    for col, emoji, label, _ in PROFILE_FIELDS:
        val = profile.get(col) if profile else None
        masked = clean_md(_mask(val)) if val else "_not set_"
        lines.append(f"{emoji} *{label}:* {masked}")

    return "\n".join(lines)


# Mapping for shorter labels in the keyboard specifically
BUTTON_LABELS = {
    "email":          "Email",
    "phone":          "Phone",
    "ton_address":    "TON",
    "usdt_address":   "USDT",
    "paypal_email":   "PayPal",
    "stars_username": "Stars",
    "bio":            "Bio",
    "alt_username":   "Alt Acc",
    "country":        "Country",
}


def _profile_keyboard() -> InlineKeyboardMarkup:
    rows = []
    current_row = []
    
    for col, _, label, _ in PROFILE_FIELDS:
        # Use a shorter label for the button if available
        short_label = BUTTON_LABELS.get(col, label)
        current_row.append(InlineKeyboardButton(f"✏️ {short_label}", callback_data=f"prof:edit:{col}"))
        
        if len(current_row) == 3:
            rows.append(current_row)
            current_row = []
            
    if current_row:
        rows.append(current_row)
        
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="nav:start")])
    return InlineKeyboardMarkup(rows)


# ── Main profile screen ───────────────────────────────────────────────────────

async def nav_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show the profile summary screen."""
    if update.callback_query:
        await update.callback_query.answer()
        user_id = update.callback_query.from_user.id
        edit_fn = update.callback_query.edit_message_text
    else:
        user_id = update.effective_user.id
        edit_fn = None

    user    = await db.get_user(user_id)
    profile = await db.get_profile(user_id)
    w_stats = await db.get_withdrawal_stats(user_id)

    text   = _profile_text(user, profile, w_stats)
    markup = _profile_keyboard()

    if edit_fn:
        try:
            await edit_fn(text, parse_mode="Markdown", reply_markup=markup)
        except Exception:
            await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


# ── Edit a field ─────────────────────────────────────────────────────────────

async def profile_edit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User tapped an edit button → ask for the new value."""
    query = update.callback_query
    await query.answer()

    field_key = query.data.split(":")[2]
    field_def = FIELD_BY_KEY.get(field_key)
    if not field_def:
        return ConversationHandler.END

    col, emoji, label, placeholder = field_def
    context.user_data["profile_edit_field"] = field_key

    if field_key == "phone":
        # Offer both Telegram share and manual entry
        text = (
            f"📞 *Edit Phone Number*\n\n"
            f"Choose how you want to share your phone number:\n\n"
            f"• Tap *📲 Share via Telegram* to use your verified Telegram number\n"
            f"• Or type your phone number manually below\n\n"
            f"_(Type /cancel to abort)_"
        )
        # Temporary reply keyboard with Telegram's native contact share button
        contact_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📲 Share via Telegram", request_contact=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=contact_keyboard)
        return AWAIT_PHONE_SHARE
        
    if field_key == "country":
        text = (
            f"🌍 *Select Your Country*\n\n"
            f"Choose your country from the list below or type it manually.\n"
            f"_(Type /cancel to abort)_"
        )
        countries = [
            "🇺🇸 USA", "🇬🇧 UK", "🇨🇦 Canada", "🇦🇺 Australia", "🇮🇳 India", 
            "🇵🇰 Pakistan", "🇧🇩 Bangladesh", "🇳🇬 Nigeria", "🇷🇺 Russia", 
            "🇮🇷 Iran", "🇰🇵 North Korea", "🇾🇪 Yemen", "🇸🇾 Syria", 
            "🇨🇳 China", "🇧🇷 Brazil", "🇮🇩 Indonesia", "🇹🇷 Turkey",
            "🇪🇬 Egypt", "🇿🇦 South Africa", "🇲🇽 Mexico", "🇩🇪 Germany",
            "🇫🇷 France", "🇮🇹 Italy", "🇪🇸 Spain", "🇦🇪 UAE", "🇸🇦 Saudi Arabia"
        ]
        # Arrange in a 2-column grid
        rows = [[KeyboardButton(c1), KeyboardButton(c2)] for c1, c2 in zip(countries[0::2], countries[1::2])]
        if len(countries) % 2 != 0:
            rows.append([KeyboardButton(countries[-1])])
        
        country_kbd = ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=country_kbd)
        return EDIT_PROFILE_VALUE

    text = (
        f"{emoji} *Edit {label}*\n\n"
        f"Current value will be replaced.\n"
        f"Please enter your new *{label}*:\n"
        f"_(e.g. {placeholder})_\n\n"
        f"_(Type /cancel to abort)_"
    )
    await query.edit_message_text(text, parse_mode="Markdown")
    return EDIT_PROFILE_VALUE


async def profile_receive_phone_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram native contact share (message.contact)."""
    contact = update.message.contact
    user_id = update.effective_user.id

    if contact and contact.phone_number:
        phone = contact.phone_number
        if not phone.startswith("+"):
            phone = "+" + phone
        await db.upsert_profile(user_id, phone=phone)
        await update.message.reply_text(
            f"✅ *Phone number saved!*\n\n📞 `{phone}`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        # Show profile
        user    = await db.get_user(user_id)
        profile = await db.get_profile(user_id)
        w_stats = await db.get_withdrawal_stats(user_id)
        
        await update.message.reply_text(
            _profile_text(user, profile, w_stats),
            parse_mode="Markdown",
            reply_markup=_profile_keyboard(),
        )
        return ConversationHandler.END

    # User typed manually instead
    return await profile_receive_value(update, context)


async def profile_receive_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle plain text input for any profile field."""
    user_id   = update.effective_user.id
    field_key = context.user_data.get("profile_edit_field")
    if not field_key:
        return ConversationHandler.END

    field_def = FIELD_BY_KEY.get(field_key)
    if not field_def:
        return ConversationHandler.END

    col, emoji, label, _ = field_def
    value = update.message.text.strip()

    if not value or len(value) < 2:
        await update.message.reply_text(
            f"⚠️ That value seems too short. Please enter a valid *{label}* or type /cancel.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove(),
        )
        return EDIT_PROFILE_VALUE

    await db.upsert_profile(user_id, **{col: value})
    context.user_data.pop("profile_edit_field", None)

    await update.message.reply_text(
        f"✅ *{label} saved!*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )

    # Reload profile screen
    user    = await db.get_user(user_id)
    profile = await db.get_profile(user_id)
    w_stats = await db.get_withdrawal_stats(user_id)
    
    await update.message.reply_text(
        _profile_text(user, profile, w_stats),
        parse_mode="Markdown",
        reply_markup=_profile_keyboard(),
    )
    return ConversationHandler.END


async def cancel_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel editing and return to profile."""
    context.user_data.pop("profile_edit_field", None)
    user_id = update.effective_user.id
    if update.message:
        await update.message.reply_text(
            "❌ Edit cancelled.", reply_markup=ReplyKeyboardRemove()
        )
    # Re-show profile
    user    = await db.get_user(user_id)
    profile = await db.get_profile(user_id)
    w_stats = await db.get_withdrawal_stats(user_id)
    
    await update.effective_message.reply_text(
        _profile_text(user, profile, w_stats),
        parse_mode="Markdown",
        reply_markup=_profile_keyboard(),
    )
    return ConversationHandler.END
