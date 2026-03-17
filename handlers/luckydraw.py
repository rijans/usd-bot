import logging
from telegram import Update, LabeledPrice, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes

from core.db import (
    has_user_entered_today,
    get_today_lucky_draw_entries_count,
    get_past_lucky_draw_winners,
    add_lucky_draw_entry
)
from core.ui import nav_keyboard

logger = logging.getLogger(__name__)

TICKET_PRICES = [
    ("🎫 Buy Entry (50 ⭐️)", 50),
    ("🎫 Buy Entry (100 ⭐️)", 100),
    ("🎫 Buy Entry (150 ⭐️)", 150),
    ("🎫 Buy Entry (300 ⭐️)", 300),
]

async def show_lucky_draw_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the main Lucky Draw interface."""
    user_id = update.effective_user.id
    
    entered_today = await has_user_entered_today(user_id)
    total_entries = await get_today_lucky_draw_entries_count()

    text = (
        "🎰 <b>Daily Lucky Draw</b> 🎰\n\n"
        "Welcome to the daily Lucky Draw! Try your luck to win big cash prizes.\n\n"
        "🥇 <b>1st Place:</b> $200 USD\n"
        "🥈 <b>2nd Place:</b> $70 USD\n"
        "🥉 <b>3rd Place:</b> $30 USD\n\n"
        "<i>Draws reset every day at midnight (UTC). You can enter the draw using Telegram Stars!</i>\n\n"
    )

    if entered_today:
        text += (
            "✅ <b>You have already entered today's draw!</b>\n"
            f"There are currently <b>{total_entries}</b> participants today. Good luck!\n\n"
            "<i>Note: Winners will be notified at the end of the day.</i>"
        )
        keyboard = [
            [InlineKeyboardButton("🎁 View Past Winners", callback_data="ld:winners")],
            [InlineKeyboardButton("🔙 Back to Home", callback_data="nav:home")]
        ]
    else:
        text += (
            "👇 Choose your entry ticket below.\n"
            "<i>⚠️ Note: Join at your own luck. Stars are non-refundable.</i>\n\n"
            f"🎟 <b>Today's Total Entries:</b> {total_entries}"
        )
        
        keyboard = []
        # Add payment buttons
        for label, stars in TICKET_PRICES:
            keyboard.append([InlineKeyboardButton(label, callback_data=f"ld:buy:{stars}")])
            
        keyboard.append([InlineKeyboardButton("🎁 View Past Winners", callback_data="ld:winners")])
        keyboard.append([InlineKeyboardButton("🔙 Back to Home", callback_data="nav:home")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode="HTML")


async def handle_buy_ticket_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a Telegram Stars invoice to the user."""
    query = update.callback_query
    await query.answer()

    stars_str = query.data.split(":")[-1]
    stars = int(stars_str)

    # Note: For Stars, provider_token must be empty string
    title = f"Lucky Draw Entry"
    description = f"Purchase 1 entry ticket into today's Lucky Draw for {stars} Telegram Stars. Non-refundable."
    payload = f"luckydraw_entry_{stars}"
    currency = "XTR"
    prices = [LabeledPrice("Ticket", stars)]

    # We send an invoice message
    await context.bot.send_invoice(
        chat_id=update.effective_chat.id,
        title=title,
        description=description,
        payload=payload,
        provider_token="",  # Required to be empty for XTR
        currency=currency,
        prices=prices,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"Pay {stars} ⭐️", pay=True)]])
    )


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Answers the PreCheckoutQuery for Telegram Stars payments."""
    query = update.pre_checkout_query
    
    if query.invoice_payload.startswith("luckydraw_entry_"):
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="Unknown payload.")


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles successful Telegram Stars payment."""
    payment = update.message.successful_payment
    user_id = update.effective_user.id
    
    if payment.invoice_payload.startswith("luckydraw_entry_"):
        stars_paid = payment.total_amount
        
        # Record entry in DB
        await add_lucky_draw_entry(user_id, stars_paid)
        
        text = (
            f"🎉 <b>Payment Successful!</b>\n\n"
            f"You have officially entered today's Lucky Draw for {stars_paid} ⭐️.\n"
            f"Results will be announced at midnight UTC. Good luck!"
        )
        
        await update.message.reply_text(
            text, 
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Home", callback_data="nav:home")]
            ])
        )


async def show_past_winners(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    winners = await get_past_lucky_draw_winners(limit=5)
    
    if not winners:
        text = "🎁 <b>Recent Lucky Draw Winners</b>\n\n<i>No draws have concluded yet. Check back tomorrow!</i>"
    else:
        text = "🎁 <b>Recent Lucky Draw Winners</b>\n\n"
        for w in winners:
            date_str = w["draw_date"].strftime("%Y-%m-%d")
            text += f"📅 <b>{date_str}</b>\n"
            text += f"🥇 $200 — {w['w1_name'] or w['w1_uname']}\n"
            text += f"🥈 $70 — {w['w2_name'] or w['w2_uname']}\n"
            text += f"🥉 $30 — {w['w3_name'] or w['w3_uname']}\n\n"
            
    # Keyboard to go back to draw menu
    keyboard = [[InlineKeyboardButton("🔙 Back to Lucky Draw", callback_data="nav:luckydraw")]]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
