"""
handlers/withdraw.py  ─  Withdrawal flow.

Rules enforced:
  • Must have completed all tasks
  • Minimum balance: $20.00
  • 15-day cooldown between withdrawals

Since bot is under development: after collecting destination, show
"Feature under development" message instead of processing.

Uses ConversationHandler states:
  PICK_METHOD  → user picks payment method
  ENTER_DEST   → user types their address/number/ID
"""
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import core.db as db
from core.ui import nav_keyboard, fmt_balance
from handlers.admin import admin_ids

# ConversationHandler states
PICK_METHOD  = 1
ENTER_DEST   = 2
USE_SAVED    = 3

METHODS = {
    "ton":    ("🔷 TON (Crypto)",       "Please enter your *TON wallet address*:"),
    "usdt":   ("💵 USDT (Crypto)",      "Please enter your *USDT wallet address*:"),
    "stars":  ("⭐️ Telegram Stars",    "Please enter your *Telegram Username* (e.g. @yourname):"),
    "paypal": ("💳 PayPal",             "Please enter your *PayPal email address*:"),
}

# Simple validators — just basic sanity checks, not production-grade
VALIDATORS = {
    "ton":    lambda s: len(s) >= 10,
    "usdt":   lambda s: len(s) >= 10,
    "stars":  lambda s: s.startswith("@") and len(s) >= 4,
    "paypal": lambda s: "@" in s and "." in s,
}


async def nav_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry: either from nav button or /withdraw command."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        send_fn = lambda t, **kw: query.edit_message_text(t, **kw)
    else:
        user_id = update.effective_user.id
        send_fn = lambda t, **kw: update.message.reply_text(t, **kw)

    is_admin = user_id in admin_ids()
    can, reason = await db.can_withdraw(user_id, is_admin=is_admin)

    if not can:
        text = _blocked_message(reason)
        await send_fn(text, parse_mode="Markdown", reply_markup=nav_keyboard())
        return ConversationHandler.END

    user = await db.get_user(user_id)
    text = (
        f"💸 *Withdraw*\n\n"
        f"💵 Your Balance: *{fmt_balance(user['balance'])}*\n"
        f"🔽 Minimum Withdrawal: *$20.00*\n"
        f"⏳ Cooldown after withdrawal: *15 days*\n\n"
        f"Select your withdrawal method:"
    )

    buttons = [
        [InlineKeyboardButton(label, callback_data=f"wdraw:method:{key}")]
        for key, (label, _) in METHODS.items()
    ]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="nav:start")])

    await send_fn(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
    return PICK_METHOD


async def pick_method(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    method_key = query.data.split(":")[2]
    if method_key not in METHODS:
        return ConversationHandler.END

    label, prompt = METHODS[method_key]
    context.user_data["withdraw_method"] = method_key
    context.user_data["withdraw_label"]  = label

    # Check if the user has a saved address for this method
    user_id = query.from_user.id
    saved   = await db.get_saved_address(user_id, method_key)

    if saved:
        context.user_data["withdraw_saved"] = saved
        masked = saved[:6] + "…" + saved[-4:] if len(saved) > 10 else saved
        await query.edit_message_text(
            f"💸 *Withdraw via {label}*\n\n"
            f"📎 *Saved address found:*\n`{masked}`\n\n"
            f"Would you like to use your saved address, or enter a new one?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Use Saved Address", callback_data="wdraw:use_saved")],
                [InlineKeyboardButton("✏️ Enter New Address",  callback_data="wdraw:enter_new")],
                [InlineKeyboardButton("❌ Cancel",             callback_data="nav:start")],
            ])
        )
        return USE_SAVED

    await query.edit_message_text(
        f"💸 *Withdraw via {label}*\n\n"
        f"{prompt}\n\n"
        f"_(Type /cancel to abort)_",
        parse_mode="Markdown",
    )
    return ENTER_DEST


async def use_saved_address(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """User chose to use their saved address or enter a new one."""
    query = update.callback_query
    await query.answer()

    if query.data == "wdraw:use_saved":
        dest         = context.user_data.pop("withdraw_saved", "")
        method_key   = context.user_data.get("withdraw_method")
        method_label = context.user_data.get("withdraw_label", "")
        user_id      = query.from_user.id

        is_admin = user_id in admin_ids()
        can, reason = await db.can_withdraw(user_id, is_admin=is_admin)
        if not can:
            await query.edit_message_text(_blocked_message(reason), parse_mode="Markdown",
                                          reply_markup=nav_keyboard())
            return ConversationHandler.END

        user   = await db.get_user(user_id)
        amount = float(user["balance"])
        await db.create_withdrawal(user_id, amount, method_label, dest)

        text = (
            f"✅ *Withdrawal Request Submitted*\n\n"
            f"💵 Amount: *{fmt_balance(amount)}*\n"
            f"📤 Method: *{method_label}*\n"
            f"🔑 Destination: `{dest}`\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Your request is pending admin review. You will be notified once processed. 🙏"
        )
        context.user_data.pop("withdraw_method", None)
        context.user_data.pop("withdraw_label",  None)
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
        return ConversationHandler.END

    else:  # wdraw:enter_new
        method_key = context.user_data.get("withdraw_method", "")
        label      = context.user_data.get("withdraw_label", "")
        _, prompt  = METHODS.get(method_key, ("", "Please enter your address:"))
        context.user_data.pop("withdraw_saved", None)
        await query.edit_message_text(
            f"💸 *Withdraw via {label}*\n\n"
            f"{prompt}\n\n"
            f"_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return ENTER_DEST

async def enter_destination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    dest = update.message.text.strip()
    method_key = context.user_data.get("withdraw_method")
    method_label = context.user_data.get("withdraw_label", "")

    if not method_key:
        return ConversationHandler.END

    # Validate input
    validator = VALIDATORS.get(method_key, lambda s: len(s) >= 3)
    if not validator(dest):
        await update.message.reply_text(
            f"⚠️ That doesn't look like a valid *{method_label}* address.\n"
            f"Please try again or type /cancel.",
            parse_mode="Markdown",
        )
        return ENTER_DEST  # Stay in state

    # Re-check eligibility (balance could change between steps)
    is_admin = user_id in admin_ids()
    can, reason = await db.can_withdraw(user_id, is_admin=is_admin)
    if not can:
        await update.message.reply_text(
            _blocked_message(reason),
            parse_mode="Markdown",
            reply_markup=nav_keyboard(),
        )
        return ConversationHandler.END

    user = await db.get_user(user_id)
    amount = float(user["balance"])

    withdrawal_id = await db.create_withdrawal(user_id, amount, method_label, dest)

    text = (
        f"✅ *Withdrawal Request Submitted*\n\n"
        f"💵 Amount: *{fmt_balance(amount)}*\n"
        f"📤 Method: *{method_label}*\n"
        f"🔑 Destination: `{dest}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Your request has been recorded and is pending admin review. You will be notified once it is processed.\n\n"
        f"Thank you for your patience! 🙏\n"
        f"━━━━━━━━━━━━━━━━━━━━━"
    )

    # Clear conversation state
    context.user_data.pop("withdraw_method", None)
    context.user_data.pop("withdraw_label",  None)

    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=nav_keyboard()
    )
    return ConversationHandler.END


async def cancel_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("withdraw_method", None)
    context.user_data.pop("withdraw_label",  None)
    if update.message:
        await update.message.reply_text("❌ Withdrawal cancelled.", reply_markup=nav_keyboard())
    return ConversationHandler.END


def _blocked_message(reason: str) -> str:
    if reason == "tasks_incomplete":
        return (
            "🔒 *Withdrawals Locked*\n\n"
            "You must complete *all tasks* before you can withdraw.\n\n"
            "👉 Tap *Tasks* in the menu to get started."
        )
    elif reason.startswith("low_balance:"):
        bal = reason.split(":")[1]
        return (
            f"💸 *Insufficient Balance*\n\n"
            f"Your balance: *${bal}*\n"
            f"Minimum required: *$20.00*\n\n"
            f"Keep earning through referrals and daily bonuses!"
        )
    elif reason.startswith("cooldown:"):
        remaining = reason.split(":")[1]
        return (
            f"⏳ *Withdrawal Cooldown Active*\n\n"
            f"You can only withdraw once every *15 days*.\n\n"
            f"⏱ Time remaining: *{remaining}*\n\n"
            f"Your balance is safe — keep earning in the meantime!"
        )
    return "❌ Withdrawal not available right now."
