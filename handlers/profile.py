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
AWAIT_LOCATION_SHARE = 52   # Waiting for Telegram location share or manual text


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
    ("location",       "📍", "Location",              "e.g. Dhaka, Bangladesh"),
]

FIELD_BY_KEY = {f[0]: f for f in PROFILE_FIELDS}


# ── Full country list (all UN-recognized + common territories) ────────────────
ALL_COUNTRIES = [
    "🇦🇫 Afghanistan", "🇦🇱 Albania", "🇩🇿 Algeria", "🇦🇩 Andorra", "🇦🇴 Angola",
    "🇦🇬 Antigua & Barbuda", "🇦🇷 Argentina", "🇦🇲 Armenia", "🇦🇺 Australia", "🇦🇹 Austria",
    "🇦🇿 Azerbaijan", "🇧🇸 Bahamas", "🇧🇭 Bahrain", "🇧🇩 Bangladesh", "🇧🇧 Barbados",
    "🇧🇾 Belarus", "🇧🇪 Belgium", "🇧🇿 Belize", "🇧🇯 Benin", "🇧🇹 Bhutan",
    "🇧🇴 Bolivia", "🇧🇦 Bosnia & Herzegovina", "🇧🇼 Botswana", "🇧🇷 Brazil", "🇧🇳 Brunei",
    "🇧🇬 Bulgaria", "🇧🇫 Burkina Faso", "🇧🇮 Burundi", "🇨🇻 Cape Verde", "🇰🇭 Cambodia",
    "🇨🇲 Cameroon", "🇨🇦 Canada", "🇨🇫 Central African Republic", "🇹🇩 Chad", "🇨🇱 Chile",
    "🇨🇳 China", "🇨🇴 Colombia", "🇰🇲 Comoros", "🇨🇬 Congo", "🇨🇩 DR Congo",
    "🇨🇷 Costa Rica", "🇭🇷 Croatia", "🇨🇺 Cuba", "🇨🇾 Cyprus", "🇨🇿 Czechia",
    "🇩🇰 Denmark", "🇩🇯 Djibouti", "🇩🇲 Dominica", "🇩🇴 Dominican Republic", "🇪🇨 Ecuador",
    "🇪🇬 Egypt", "🇸🇻 El Salvador", "🇬🇶 Equatorial Guinea", "🇪🇷 Eritrea", "🇪🇪 Estonia",
    "🇸🇿 Eswatini", "🇪🇹 Ethiopia", "🇫🇯 Fiji", "🇫🇮 Finland", "🇫🇷 France",
    "🇬🇦 Gabon", "🇬🇲 Gambia", "🇬🇪 Georgia", "🇩🇪 Germany", "🇬🇭 Ghana",
    "🇬🇷 Greece", "🇬🇩 Grenada", "🇬🇹 Guatemala", "🇬🇳 Guinea", "🇬🇼 Guinea-Bissau",
    "🇬🇾 Guyana", "🇭🇹 Haiti", "🇭🇳 Honduras", "🇭🇺 Hungary", "🇮🇸 Iceland",
    "🇮🇳 India", "🇮🇩 Indonesia", "🇮🇷 Iran", "🇮🇶 Iraq", "🇮🇪 Ireland",
    "🇮🇱 Israel", "🇮🇹 Italy", "🇯🇲 Jamaica", "🇯🇵 Japan", "🇯🇴 Jordan",
    "🇰🇿 Kazakhstan", "🇰🇪 Kenya", "🇰🇮 Kiribati", "🇽🇰 Kosovo", "🇰🇼 Kuwait",
    "🇰🇬 Kyrgyzstan", "🇱🇦 Laos", "🇱🇻 Latvia", "🇱🇧 Lebanon", "🇱🇸 Lesotho",
    "🇱🇷 Liberia", "🇱🇾 Libya", "🇱🇮 Liechtenstein", "🇱🇹 Lithuania", "🇱🇺 Luxembourg",
    "🇲🇬 Madagascar", "🇲🇼 Malawi", "🇲🇾 Malaysia", "🇲🇻 Maldives", "🇲🇱 Mali",
    "🇲🇹 Malta", "🇲🇭 Marshall Islands", "🇲🇷 Mauritania", "🇲🇺 Mauritius", "🇲🇽 Mexico",
    "🇫🇲 Micronesia", "🇲🇩 Moldova", "🇲🇨 Monaco", "🇲🇳 Mongolia", "🇲🇪 Montenegro",
    "🇲🇦 Morocco", "🇲🇿 Mozambique", "🇲🇲 Myanmar", "🇳🇦 Namibia", "🇳🇷 Nauru",
    "🇳🇵 Nepal", "🇳🇱 Netherlands", "🇳🇿 New Zealand", "🇳🇮 Nicaragua", "🇳🇪 Niger",
    "🇳🇬 Nigeria", "🇰🇵 North Korea", "🇲🇰 North Macedonia", "🇳🇴 Norway", "🇴🇲 Oman",
    "🇵🇰 Pakistan", "🇵🇼 Palau", "🇵🇸 Palestine", "🇵🇦 Panama", "🇵🇬 Papua New Guinea",
    "🇵🇾 Paraguay", "🇵🇪 Peru", "🇵🇭 Philippines", "🇵🇱 Poland", "🇵🇹 Portugal",
    "🇶🇦 Qatar", "🇷🇴 Romania", "🇷🇺 Russia", "🇷🇼 Rwanda", "🇰🇳 Saint Kitts & Nevis",
    "🇱🇨 Saint Lucia", "🇻🇨 Saint Vincent & Grenadines", "🇼🇸 Samoa", "🇸🇲 San Marino",
    "🇸🇹 Sao Tome & Principe", "🇸🇦 Saudi Arabia", "🇸🇳 Senegal", "🇷🇸 Serbia", "🇸🇨 Seychelles",
    "🇸🇱 Sierra Leone", "🇸🇬 Singapore", "🇸🇰 Slovakia", "🇸🇮 Slovenia", "🇸🇧 Solomon Islands",
    "🇸🇴 Somalia", "🇿🇦 South Africa", "🇸🇸 South Sudan", "🇪🇸 Spain", "🇱🇰 Sri Lanka",
    "🇸🇩 Sudan", "🇸🇷 Suriname", "🇸🇪 Sweden", "🇨🇭 Switzerland", "🇸🇾 Syria",
    "🇹🇼 Taiwan", "🇹🇯 Tajikistan", "🇹🇿 Tanzania", "🇹🇭 Thailand", "🇹🇱 Timor-Leste",
    "🇹🇬 Togo", "🇹🇴 Tonga", "🇹🇹 Trinidad & Tobago", "🇹🇳 Tunisia", "🇹🇷 Turkey",
    "🇹🇲 Turkmenistan", "🇹🇻 Tuvalu", "🇺🇬 Uganda", "🇺🇦 Ukraine", "🇦🇪 UAE",
    "🇬🇧 UK", "🇺🇸 USA", "🇺🇾 Uruguay", "🇺🇿 Uzbekistan", "🇻🇺 Vanuatu",
    "🇻🇦 Vatican City", "🇻🇪 Venezuela", "🇻🇳 Vietnam", "🇾🇪 Yemen", "🇿🇲 Zambia",
    "🇿🇼 Zimbabwe",
]

# Phone country-code prefix → country label (longest prefix wins)
_PHONE_PREFIX_MAP: list[tuple[str, str]] = [
    ("+880", "🇧🇩 Bangladesh"), ("+91", "🇮🇳 India"), ("+92", "🇵🇰 Pakistan"),
    ("+234", "🇳🇬 Nigeria"), ("+7", "🇷🇺 Russia"), ("+98", "🇮🇷 Iran"),
    ("+86", "🇨🇳 China"), ("+55", "🇧🇷 Brazil"), ("+62", "🇮🇩 Indonesia"),
    ("+90", "🇹🇷 Turkey"), ("+20", "🇪🇬 Egypt"), ("+27", "🇿🇦 South Africa"),
    ("+52", "🇲🇽 Mexico"), ("+49", "🇩🇪 Germany"), ("+33", "🇫🇷 France"),
    ("+39", "🇮🇹 Italy"), ("+34", "🇪🇸 Spain"), ("+971", "🇦🇪 UAE"),
    ("+966", "🇸🇦 Saudi Arabia"), ("+44", "🇬🇧 UK"), ("+1", "🇺🇸 USA"),
    ("+81", "🇯🇵 Japan"), ("+82", "🇰🇷 South Korea"), ("+63", "🇵🇭 Philippines"),
    ("+84", "🇻🇳 Vietnam"), ("+60", "🇲🇾 Malaysia"), ("+66", "🇹🇭 Thailand"),
    ("+380", "🇺🇦 Ukraine"), ("+994", "🇦🇿 Azerbaijan"), ("+998", "🇺🇿 Uzbekistan"),
    ("+996", "🇰🇬 Kyrgyzstan"), ("+993", "🇹🇲 Turkmenistan"), ("+992", "🇹🇯 Tajikistan"),
    ("+77", "🇰🇿 Kazakhstan"), ("+374", "🇦🇲 Armenia"), ("+995", "🇬🇪 Georgia"),
    ("+961", "🇱🇧 Lebanon"), ("+962", "🇯🇴 Jordan"), ("+963", "🇸🇾 Syria"),
    ("+964", "🇮🇶 Iraq"), ("+965", "🇰🇼 Kuwait"), ("+968", "🇴🇲 Oman"),
    ("+974", "🇶🇦 Qatar"), ("+973", "🇧🇭 Bahrain"), ("+967", "🇾🇪 Yemen"),
    ("+970", "🇵🇸 Palestine"), ("+972", "🇮🇱 Israel"), ("+212", "🇲🇦 Morocco"),
    ("+216", "🇹🇳 Tunisia"), ("+213", "🇩🇿 Algeria"), ("+218", "🇱🇾 Libya"),
    ("+249", "🇸🇩 Sudan"), ("+251", "🇪🇹 Ethiopia"), ("+254", "🇰🇪 Kenya"),
    ("+255", "🇹🇿 Tanzania"), ("+256", "🇺🇬 Uganda"), ("+260", "🇿🇲 Zambia"),
    ("+263", "🇿🇼 Zimbabwe"), ("+237", "🇨🇲 Cameroon"), ("+233", "🇬🇭 Ghana"),
    ("+225", "🇨🇮 Ivory Coast"), ("+221", "🇸🇳 Senegal"), ("+243", "🇨🇩 DR Congo"),
    ("+250", "🇷🇼 Rwanda"), ("+94", "🇱🇰 Sri Lanka"), ("+95", "🇲🇲 Myanmar"),
    ("+977", "🇳🇵 Nepal"), ("+975", "🇧🇹 Bhutan"), ("+960", "🇲🇻 Maldives"),
    ("+61", "🇦🇺 Australia"), ("+64", "🇳🇿 New Zealand"), ("+48", "🇵🇱 Poland"),
    ("+30", "🇬🇷 Greece"), ("+31", "🇳🇱 Netherlands"), ("+32", "🇧🇪 Belgium"),
    ("+46", "🇸🇪 Sweden"), ("+47", "🇳🇴 Norway"), ("+45", "🇩🇰 Denmark"),
    ("+358", "🇫🇮 Finland"), ("+351", "🇵🇹 Portugal"), ("+43", "🇦🇹 Austria"),
    ("+41", "🇨🇭 Switzerland"), ("+420", "🇨🇿 Czechia"), ("+36", "🇭🇺 Hungary"),
    ("+40", "🇷🇴 Romania"), ("+381", "🇷🇸 Serbia"), ("+385", "🇭🇷 Croatia"),
    ("+387", "🇧🇦 Bosnia & Herzegovina"), ("+54", "🇦🇷 Argentina"), ("+56", "🇨🇱 Chile"),
    ("+57", "🇨🇴 Colombia"), ("+51", "🇵🇪 Peru"), ("+58", "🇻🇪 Venezuela"),
]
# Sort longest prefix first so +880 matches before +8
_PHONE_PREFIX_MAP.sort(key=lambda x: -len(x[0]))

# Telegram language_code → country label
_LANG_TO_COUNTRY: dict[str, str] = {
    "bn": "🇧🇩 Bangladesh", "hi": "🇮🇳 India", "ur": "🇵🇰 Pakistan",
    "ar": "🇸🇦 Saudi Arabia", "fa": "🇮🇷 Iran", "zh": "🇨🇳 China",
    "zh-hans": "🇨🇳 China", "zh-hant": "🇹🇼 Taiwan", "pt": "🇧🇷 Brazil",
    "pt-br": "🇧🇷 Brazil", "pt-pt": "🇵🇹 Portugal", "id": "🇮🇩 Indonesia",
    "tr": "🇹🇷 Turkey", "ru": "🇷🇺 Russia", "de": "🇩🇪 Germany",
    "fr": "🇫🇷 France", "it": "🇮🇹 Italy", "es": "🇪🇸 Spain",
    "en": "🇺🇸 USA", "ja": "🇯🇵 Japan", "ko": "🇰🇷 South Korea",
    "vi": "🇻🇳 Vietnam", "th": "🇹🇭 Thailand", "ms": "🇲🇾 Malaysia",
    "uk": "🇺🇦 Ukraine", "pl": "🇵🇱 Poland", "ro": "🇷🇴 Romania",
    "nl": "🇳🇱 Netherlands", "el": "🇬🇷 Greece", "sv": "🇸🇪 Sweden",
    "da": "🇩🇰 Denmark", "fi": "🇫🇮 Finland", "nb": "🇳🇴 Norway",
    "cs": "🇨🇿 Czechia", "sk": "🇸🇰 Slovakia", "hu": "🇭🇺 Hungary",
    "bg": "🇧🇬 Bulgaria", "hr": "🇭🇷 Croatia", "sr": "🇷🇸 Serbia",
    "he": "🇮🇱 Israel", "az": "🇦🇿 Azerbaijan", "uz": "🇺🇿 Uzbekistan",
    "kk": "🇰🇿 Kazakhstan", "hy": "🇦🇲 Armenia", "ka": "🇬🇪 Georgia",
    "ne": "🇳🇵 Nepal", "si": "🇱🇰 Sri Lanka", "my": "🇲🇲 Myanmar",
    "km": "🇰🇭 Cambodia", "lo": "🇱🇦 Laos", "mn": "🇲🇳 Mongolia",
    "tg": "🇹🇯 Tajikistan", "tk": "🇹🇲 Turkmenistan", "ky": "🇰🇬 Kyrgyzstan",
    "am": "🇪🇹 Ethiopia", "sw": "🇰🇪 Kenya", "ha": "🇳🇬 Nigeria",
    "yo": "🇳🇬 Nigeria", "ig": "🇳🇬 Nigeria",
}


def _guess_country(profile, lang_code: str) -> str | None:
    """Guess country from saved phone prefix (priority) or Telegram language code."""
    # 1. Try phone number prefix
    phone = (profile.get("phone") or "") if profile else ""
    if phone:
        phone = phone.strip()
        if not phone.startswith("+"):
            phone = "+" + phone
        for prefix, country in _PHONE_PREFIX_MAP:
            if phone.startswith(prefix):
                return country
    # 2. Try language code
    if lang_code:
        country = _LANG_TO_COUNTRY.get(lang_code.lower())
        if country:
            return country
        # Try base language (e.g. 'pt-br' → 'pt')
        base = lang_code.split("-")[0].lower()
        return _LANG_TO_COUNTRY.get(base)
    return None


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
        f"🆔 *User ID:* `{user['user_id']}`",
        f"📅 *Member since:* {joined}",
        f"💰 *Balance:* {fmt_balance(user['balance'])}",
        f"✅ *Paid Withdrawals:* {fmt_balance(paid)}",
        f"❌ *Rejected Withdrawals:* {fmt_balance(rejected)}",
        f"\n━━━━━━━━━━━━━━\n",
    ]

    for col, emoji, label, _ in PROFILE_FIELDS:
        val = profile.get(col) if profile else None
        if not val:
            masked = "_not set_"
        elif col == "location" and (val.startswith("http://") or val.startswith("https://")):
            # Make URL clickable and don't mask it
            masked = f"[📍 Open Maps]({val})"
        else:
            masked = clean_md(_mask(val))
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
    "location":       "Location",
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
        # Guess country from phone number or Telegram language code
        profile_data = await db.get_profile(update.effective_user.id)
        lang_code = update.effective_user.language_code or ""
        guessed = _guess_country(profile_data, lang_code)

        hint = f"\n\n💡 *Detected country:* {guessed} (shown first)" if guessed else ""
        text = (
            f"🌍 *Select Your Country*\n\n"
            f"Choose from the full list or type your country manually.{hint}\n\n"
            f"_(Type /cancel to abort)_"
        )

        # Put guessed country first, then the full list
        ordered = ([guessed] + [c for c in ALL_COUNTRIES if c != guessed]) if guessed else list(ALL_COUNTRIES)

        # Build 2-column grid
        rows = [[KeyboardButton(c1), KeyboardButton(c2)] for c1, c2 in zip(ordered[0::2], ordered[1::2])]
        if len(ordered) % 2 != 0:
            rows.append([KeyboardButton(ordered[-1])])

        country_kbd = ReplyKeyboardMarkup(rows, resize_keyboard=True, one_time_keyboard=True)
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=country_kbd)
        return EDIT_PROFILE_VALUE

    if field_key == "location":
        text = (
            f"📍 *Edit Location*\n\n"
            f"Share your location accurately:\n\n"
            f"• Tap *📍 Share my location* to use your current GPS\n"
            f"• Or type your city/area manually below\n\n"
            f"_(Type /cancel to abort)_"
        )
        loc_keyboard = ReplyKeyboardMarkup(
            [[KeyboardButton("📍 Share my location", request_location=True)]],
            resize_keyboard=True,
            one_time_keyboard=True,
        )
        await query.message.reply_text(text, parse_mode="Markdown", reply_markup=loc_keyboard)
        return AWAIT_LOCATION_SHARE

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


async def profile_receive_location_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Telegram native location share (message.location)."""
    loc = update.message.location
    user_id = update.effective_user.id

    if loc:
        # We'll save as text "Lat: X, Lon: Y" roughly or just a link?
        # A Google Maps link is most useful for admins
        val = f"https://www.google.com/maps?q={loc.latitude},{loc.longitude}"
        await db.upsert_profile(user_id, location=val)
        await update.message.reply_text(
            f"✅ *Location saved!*\n\n📍 `{val}`",
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
