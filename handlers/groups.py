"""
handlers/groups.py  ─  Group Owner Auto-Promoter Settings

Allows group owners who added the bot to configure auto-posting of their
referral link inside each group via a private-chat inline keyboard.
"""
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import BOT_USERNAME, invite_link


INTERVAL_OPTIONS = [
    ("30 min",  0),    # stored as 0 hours, we'll use a special case
    ("1 hour",  1),
    ("3 hours", 3),
    ("6 hours", 6),
    ("12 hours", 12),
    ("24 hours", 24),
]

# We store half-hours as 0 in interval_hours — handled specially in job.
# Actually let's keep it simple and store minutes in a separate field. 
# Instead, store minutes: map interval_hours=0 → 30 min sentinel.
# Simplest: store all as hours. Use 0.5 by promoting to minutes stored as 0 → 30 min via separate logic.
# For simplicity: Only integer hour options. Remove 30 min to keep the DB clean.

INTERVALS = [
    ("1 hour",  1),
    ("3 hours", 3),
    ("6 hours", 6),
    ("12 hours", 12),
    ("24 hours", 24),
]


def _group_list_keyboard(groups, owner_id: int) -> InlineKeyboardMarkup:
    """Build an inline keyboard listing the user's registered groups."""
    buttons = []
    for g in groups:
        status_icon = "🟢" if g["active"] else "🔴"
        group_title = g["title"] or f"Group {g['chat_id']}"
        label = f"{status_icon} {group_title}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"grp:detail:{g['chat_id']}")])
    buttons.append([InlineKeyboardButton("🔙 Back", callback_data="nav:start")])
    return InlineKeyboardMarkup(buttons)


def _group_detail_keyboard(group) -> InlineKeyboardMarkup:
    """Build the settings keyboard for a single group."""
    chat_id = group["chat_id"]
    toggle_label = "⏸ Pause Auto-Post" if group["active"] else "▶️ Enable Auto-Post"
    current_h = group["interval_hours"]

    interval_buttons = []
    for label, hours in INTERVALS:
        mark = "✅ " if hours == current_h else ""
        interval_buttons.append(
            InlineKeyboardButton(f"{mark}{label}", callback_data=f"grp:interval:{chat_id}:{hours}")
        )
    # Group into rows of 3
    interval_rows = [interval_buttons[i:i+3] for i in range(0, len(interval_buttons), 3)]

    return InlineKeyboardMarkup([
        *interval_rows,
        [InlineKeyboardButton(toggle_label, callback_data=f"grp:toggle:{chat_id}")],
        [InlineKeyboardButton("🗑 Remove Bot", callback_data=f"grp:delete:{chat_id}")],
        [InlineKeyboardButton("🔙 Back to Groups", callback_data="grp:list")],
    ])


async def nav_groups(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point — show all groups this user has registered."""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    if not user:
        return

    groups = await db.get_groups_by_owner(user_id)

    if update.callback_query:
        await update.callback_query.answer()
        edit_fn = update.callback_query.edit_message_text
    else:
        edit_fn = None

    if not groups:
        text = (
            "👥 *For Group Owners*\n\n"
            "You have no groups registered yet.\n\n"
            "To get started:\n"
            "1️⃣ Add the bot to your Telegram group\n"
            "2️⃣ Make the bot an *Administrator* (so it can post)\n"
            "3️⃣ Come back here to configure the auto-post interval!\n\n"
            "The bot will automatically post your referral link at the interval you choose."
        )
        markup = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="nav:start")]])
    else:
        text = (
            f"👥 *For Group Owners*\n\n"
            f"You have *{len(groups)}* group(s) registered.\n"
            f"Tap a group below to configure its auto-post settings.\n\n"
            f"🟢 = Active  |  🔴 = Paused"
        )
        markup = _group_list_keyboard(groups, user_id)

    if edit_fn:
        await edit_fn(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def group_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all grp:* callback queries."""
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data == "grp:list":
        await nav_groups(update, context)
        return

    if data.startswith("grp:detail:"):
        chat_id = int(data.split(":")[2])
        group = await db.get_group(chat_id)
        if not group or group["owner_id"] != user_id:
            await query.answer("Group not found or you are not the owner.", show_alert=True)
            return

        hours = group["interval_hours"]
        label = next((l for l, h in INTERVALS if h == hours), f"{hours}h")
        text = (
            f"📢 *{group['title'] or f'Group {chat_id}'}*\n\n"
            f"Status: {'🟢 Active' if group['active'] else '🔴 Paused'}\n"
            f"Auto-post interval: *{label}*\n\n"
            f"Choose an interval for auto-posting your referral link:"
        )
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=_group_detail_keyboard(group))
        return

    if data.startswith("grp:interval:"):
        parts = data.split(":")
        chat_id = int(parts[2])
        hours = int(parts[3])
        group = await db.get_group(chat_id)
        if not group or group["owner_id"] != user_id:
            await query.answer("Unauthorized.", show_alert=True)
            return
        await db.update_group_interval(chat_id, hours)
        await query.answer(f"✅ Interval updated to {hours}h!", show_alert=False)
        # Reload detail
        group = await db.get_group(chat_id)
        label = next((l for l, h in INTERVALS if h == hours), f"{hours}h")
        text = (
            f"📢 *{group['title'] or f'Group {chat_id}'}*\n\n"
            f"Status: {'🟢 Active' if group['active'] else '🔴 Paused'}\n"
            f"Auto-post interval: *{label}*\n\n"
            f"Choose an interval for auto-posting your referral link:"
        )
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=_group_detail_keyboard(group))
        return

    if data.startswith("grp:toggle:"):
        chat_id = int(data.split(":")[2])
        group = await db.get_group(chat_id)
        if not group or group["owner_id"] != user_id:
            await query.answer("Unauthorized.", show_alert=True)
            return
        updated = await db.toggle_group(chat_id)
        state = "Active 🟢" if updated["active"] else "Paused 🔴"
        await query.answer(f"Group is now {state}", show_alert=False)
        # Reload
        group = await db.get_group(chat_id)
        hours = group["interval_hours"]
        label = next((l for l, h in INTERVALS if h == hours), f"{hours}h")
        text = (
            f"📢 *{group['title'] or f'Group {chat_id}'}*\n\n"
            f"Status: {'🟢 Active' if group['active'] else '🔴 Paused'}\n"
            f"Auto-post interval: *{label}*\n\n"
            f"Choose an interval for auto-posting your referral link:"
        )
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=_group_detail_keyboard(group))
        return

    if data.startswith("grp:delete:"):
        chat_id = int(data.split(":")[2])
        group = await db.get_group(chat_id)
        if not group or group["owner_id"] != user_id:
            await query.answer("Unauthorized.", show_alert=True)
            return
        await db.delete_group(chat_id)
        await query.answer("✅ Group removed from your list.", show_alert=True)
        await nav_groups(update, context)
        return
