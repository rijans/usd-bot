"""
handlers/admin.py  ─  Admin-only panel via /admin command.

Features:
  • 📊 Bot statistics
  • 📋 Manage tasks (add / toggle / delete channel tasks)
  • 💸 Review pending withdrawals (approve / reject)
  • 📢 Broadcast message to all users

Access: ADMIN_IDS env var (comma-separated Telegram user IDs)

ConversationHandler states:
  ADD_TASK_TITLE    → admin types task title
  ADD_TASK_CHAT     → admin types @username or chat_id
  ADD_TASK_LINK     → admin types invite link
  BROADCAST_TEXT    → admin types broadcast message
"""
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, filters, MessageHandler, CommandHandler

import core.db as db
from core.ui import fmt_balance

# States
ADD_TASK_TITLE  = 20
ADD_TASK_CHAT   = 21
ADD_TASK_LINK   = 22
BROADCAST_TEXT  = 30
EDIT_SETTING    = 40
WREJECT_REASON  = 50
EDIT_TASK_TITLE = 60
EDIT_TASK_CHAT  = 61
EDIT_TASK_LINK  = 62


def admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        uid = update.effective_user.id
        if uid not in admin_ids():
            if update.message:
                await update.message.reply_text("⛔ Unauthorized.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Unauthorized.", show_alert=True)
            return ConversationHandler.END
        return await func(update, context)
    wrapper.__name__ = func.__name__
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Entry: /admin
# ─────────────────────────────────────────────────────────────────────────────

@require_admin
async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = await db.get_stats()
    text = (
        f"🔧 *Admin Panel*\n\n"
        f"👥 Total Users: *{stats['total_users']}*\n"
        f"✅ Active (tasks done): *{stats['active_users']}*\n"
        f"💰 Total Balance Owed: *{fmt_balance(stats['total_balance_owed'])}*\n"
        f"💸 Pending Withdrawals: *{stats['pending_withdrawals']}*\n"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=_admin_keyboard()
    )


def _admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Manage Tasks", callback_data="adm:tasks")],
        [InlineKeyboardButton("💸 Withdrawals", callback_data="adm:withdrawals")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings")],
        [InlineKeyboardButton("📊 Full Stats", callback_data="adm:stats")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Admin callbacks (entry point for ConversationHandler)
# ─────────────────────────────────────────────────────────────────────────────

@require_admin
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Task list ─────────────────────────────────────────────────────────────
    if data == "adm:tasks":
        tasks = await db.get_active_tasks()
        all_tasks = await _all_tasks_including_inactive()
        text = f"📋 *Tasks* ({len(tasks)} active)\n\n"
        buttons = []
        for t in all_tasks:
            status = "✅" if t["active"] else "❌"
            buttons.append([
                InlineKeyboardButton(
                    f"{status} {t['title']} ({t['chat_id']})",
                    callback_data=f"adm:task_detail:{t['id']}"
                )
            ])
        buttons.append([InlineKeyboardButton("➕ Add New Task", callback_data="adm:add_task")])
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="adm:back")])
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    # ── Task detail ───────────────────────────────────────────────────────────
    elif data.startswith("adm:task_detail:"):
        task_id = int(data.split(":")[2])
        task = await db.get_task(task_id)
        if not task:
            await query.answer("Not found.", show_alert=True)
            return ConversationHandler.END
        status = "✅ Active" if task["active"] else "❌ Inactive"
        # Show global task reward from settings (not the per-task column which defaults to 0)
        task_reward_str = await db.get_setting("task_reward", "0.30")
        text = (
            f"📌 *{task['title']}*\n\n"
            f"Chat ID: `{task['chat_id']}`\n"
            f"Link: {task['invite_link']}\n"
            f"Reward: {fmt_balance(float(task_reward_str))} _(global setting)_\n"
            f"Status: {status}"
        )
        toggle_label = "⏸ Deactivate" if task["active"] else "▶️ Activate"
        context.user_data["adm_prev_menu"] = "adm:tasks"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✏️ Edit Title",   callback_data=f"adm:edit_task_title:{task_id}"),
                 InlineKeyboardButton("🔢 Edit Chat ID", callback_data=f"adm:edit_task_chat:{task_id}")],
                [InlineKeyboardButton("🔗 Edit URL",     callback_data=f"adm:edit_task_link:{task_id}")],
                [InlineKeyboardButton(toggle_label,       callback_data=f"adm:toggle:{task_id}"),
                 InlineKeyboardButton("🗑 Delete",        callback_data=f"adm:delete:{task_id}")],
                [InlineKeyboardButton("⬅️ Back",          callback_data="adm:tasks")],
            ])
        )
        return ConversationHandler.END

    # ── Toggle task ───────────────────────────────────────────────────────────
    elif data.startswith("adm:toggle:"):
        task_id = int(data.split(":")[2])
        result = await db.toggle_task(task_id)
        state = "activated ✅" if result["active"] else "deactivated ❌"
        await query.answer(f"Task {state}!", show_alert=True)
        query.data = f"adm:task_detail:{task_id}"
        return await admin_callback(update, context)

    # ── Delete task ───────────────────────────────────────────────────────────
    elif data.startswith("adm:delete:"):
        task_id = int(data.split(":")[2])
        ok = await db.delete_task(task_id)
        await query.answer("Deleted!" if ok else "Failed.", show_alert=True)
        query.data = "adm:tasks"
        return await admin_callback(update, context)

    # ── Edit task fields ──────────────────────────────────────────────────────
    elif data.startswith("adm:edit_task_title:"):
        task_id = int(data.split(":")[2])
        task = await db.get_task(task_id)
        context.user_data["edit_task_id"] = task_id
        context.user_data["adm_prev_menu"] = f"adm:task_detail:{task_id}"
        await query.edit_message_text(
            f"✏️ *Edit Task Title*\n\n"
            f"Current: `{task['title']}`\n\n"
            f"Send the new title:\n\n_(Type /cancel to abort)_",
            parse_mode="Markdown"
        )
        return EDIT_TASK_TITLE

    elif data.startswith("adm:edit_task_chat:"):
        task_id = int(data.split(":")[2])
        task = await db.get_task(task_id)
        context.user_data["edit_task_id"] = task_id
        context.user_data["adm_prev_menu"] = f"adm:task_detail:{task_id}"
        await query.edit_message_text(
            f"🔢 *Edit Chat ID*\n\n"
            f"Current: `{task['chat_id']}`\n\n"
            f"Send the new @username or numeric chat ID:\n\n_(Type /cancel to abort)_",
            parse_mode="Markdown"
        )
        return EDIT_TASK_CHAT

    elif data.startswith("adm:edit_task_link:"):
        task_id = int(data.split(":")[2])
        task = await db.get_task(task_id)
        context.user_data["edit_task_id"] = task_id
        context.user_data["adm_prev_menu"] = f"adm:task_detail:{task_id}"
        await query.edit_message_text(
            f"🔗 *Edit Invite URL*\n\n"
            f"Current: `{task['invite_link']}`\n\n"
            f"Send the new invite link (must start with `https://t.me/`):\n\n_(Type /cancel to abort)_",
            parse_mode="Markdown"
        )
        return EDIT_TASK_LINK

    # ── Add task: start ───────────────────────────────────────────────────────
    elif data == "adm:add_task":
        context.user_data["adm_prev_menu"] = "adm:tasks"
        await query.edit_message_text(
            "📋 *Add New Task*\n\n"
            "Step 1/3 — Send the *task title* (e.g. 'Join Our Announcement Channel'):\n\n"
            "_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return ADD_TASK_TITLE

    # ── Withdrawals ───────────────────────────────────────────────────────────
    elif data == "adm:withdrawals":
        await _show_withdrawals(query)
        return ConversationHandler.END

    elif data.startswith("adm:wpay:") or data.startswith("adm:wreject:"):
        action = "paid" if data.startswith("adm:wpay:") else "rejected"
        wid = int(data.split(":")[2])
        
        if action == "rejected":
            context.user_data["wreject_id"] = wid
            await query.edit_message_text(
                f"❌ *Reject Withdrawal #{wid}*\n\n"
                f"Please enter the reason for rejection (this will be sent to the user).\n\n"
                f"_(Type /cancel to abort)_",
                parse_mode="Markdown"
            )
            return WREJECT_REASON

        result = await db.process_withdrawal(wid, "paid")
        if result:
            await query.answer("Withdrawal paid!", show_alert=True)
            # Notify user
            status_msg = (
                "✅ *Withdrawal Approved!*\n\n"
                f"Your payment of {fmt_balance(result['amount'])} via {result['method']} "
                f"to `{result['destination']}` has been successfully processed."
            )
            try:
                await context.bot.send_message(result["user_id"], status_msg, parse_mode="Markdown")
            except Exception:
                pass
        await _show_withdrawals(query)
        return ConversationHandler.END

    # ── Broadcast: start ──────────────────────────────────────────────────────
    elif data == "adm:broadcast":
        context.user_data["adm_prev_menu"] = "adm:back"
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Send the message to broadcast to all users.\n"
            "Supports Markdown formatting.\n\n"
            "_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return BROADCAST_TEXT

    # ── Full Stats ────────────────────────────────────────────────────────────
    elif data == "adm:stats":
        stats = await db.get_stats()
        top_inviters = await db.get_leaderboard(10)
        top_earners = await db.get_earners_leaderboard(10)
        
        text = (
            f"📊 *Full Statistics*\n\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"✅ Active (tasks done): {stats['active_users']}\n"
            f"💰 Total Balance Owed: {fmt_balance(stats['total_balance_owed'])}\n"
            f"💸 Pending Withdrawals: {stats['pending_withdrawals']}\n\n"
            f"🏆 *Top 10 Inviters:*\n"
        )
        for i, u in enumerate(top_inviters, 1):
            text += f"{i}. {u['full_name']} — {u['total_invites']} invites\n"
            
        text += f"\n💰 *Top 10 Earners:*\n"
        for i, u in enumerate(top_earners, 1):
            text += f"{i}. {u['full_name']} — {fmt_balance(u['balance'])}\n"
            
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]])
        )
        return ConversationHandler.END

    # ── Settings ──────────────────────────────────────────────────────────────
    elif data == "adm:settings":
        signup = await db.get_setting("signup_bonus", "1.00")
        task = await db.get_setting("task_reward", "0.30")
        dp = await db.get_setting("daily_bonus_primary", "0.20")
        ds = await db.get_setting("daily_bonus_secondary", "0.02")
        dt = await db.get_setting("daily_bonus_threshold", "5")
        rp = await db.get_setting("referral_reward_primary", "0.30")
        rs = await db.get_setting("referral_reward_secondary", "0.05")
        rt = await db.get_setting("referral_reward_threshold", "5")
        
        text = (
            f"⚙️ *Bot Settings*\n\n"
            f"🎉 Signup Bonus: `{fmt_balance(signup)}`\n"
            f"📋 Task Reward: `{fmt_balance(task)}`\n\n"
            f"🎁 *Daily Bonus (Tiered):*\n"
            f"  First {dt} days: `{fmt_balance(dp)}`\n"
            f"  After: `{fmt_balance(ds)}`\n\n"
            f"👥 *Referral Reward (Tiered):*\n"
            f"  First {rt} referrals: `{fmt_balance(rp)}`\n"
            f"  After: `{fmt_balance(rs)}`\n\n"
            f"Choose a setting to edit:"
        )
        fake_label = "🟢 Fake Leaders: ON" if await db.get_setting("show_fake_leaders", "1") == "1" else "🔴 Fake Leaders: OFF"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🎉 Signup Bonus", callback_data="adm:edit_set:signup_bonus")],
            [InlineKeyboardButton("📋 Task Reward", callback_data="adm:edit_set:task_reward")],
            [InlineKeyboardButton("🎁 Daily Primary", callback_data="adm:edit_set:daily_bonus_primary"),
             InlineKeyboardButton("🎁 Daily Secondary", callback_data="adm:edit_set:daily_bonus_secondary")],
            [InlineKeyboardButton("🎁 Daily Threshold", callback_data="adm:edit_set:daily_bonus_threshold")],
            [InlineKeyboardButton("👥 Ref Primary", callback_data="adm:edit_set:referral_reward_primary"),
             InlineKeyboardButton("👥 Ref Secondary", callback_data="adm:edit_set:referral_reward_secondary")],
            [InlineKeyboardButton("👥 Ref Threshold", callback_data="adm:edit_set:referral_reward_threshold")],
            [InlineKeyboardButton(fake_label, callback_data="adm:toggle_fake")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return ConversationHandler.END

    elif data == "adm:toggle_fake":
        current = await db.get_setting("show_fake_leaders", "1")
        new_val = "0" if current == "1" else "1"
        await db.set_setting("show_fake_leaders", new_val)
        await query.answer(f"Fake leaders {'enabled' if new_val == '1' else 'disabled'}!")
        query.data = "adm:settings"
        return await admin_callback(update, context)

    elif data.startswith("adm:edit_set:"):
        key = data.split(":")[2]
        context.user_data["edit_setting_key"] = key
        context.user_data["adm_prev_menu"] = "adm:settings"
        
        labels = {
            "signup_bonus": "Signup Bonus",
            "task_reward": "Task Reward",
            "daily_bonus_primary": "Daily Bonus (Primary)", 
            "daily_bonus_secondary": "Daily Bonus (After Threshold)",
            "daily_bonus_threshold": "Daily Bonus Threshold (days)",
            "referral_reward_primary": "Referral Reward (Primary)",
            "referral_reward_secondary": "Referral Reward (After Threshold)",
            "referral_reward_threshold": "Referral Threshold (referrals)",
        }
        # Show current value
        defaults = {
            "signup_bonus": "1.00", "task_reward": "0.30",
            "daily_bonus_primary": "0.20", "daily_bonus_secondary": "0.02",
            "daily_bonus_threshold": "5", "referral_reward_primary": "0.30",
            "referral_reward_secondary": "0.05", "referral_reward_threshold": "5",
        }
        current_val = await db.get_setting(key, defaults.get(key, "0"))
        await query.edit_message_text(
            f"⚙️ *Edit {labels.get(key, key)}*\n\n"
            f"Current value: `{current_val}`\n\n"
            f"Send the new value (number).\n\n"
            f"_(Type /cancel to abort)_",
            parse_mode="Markdown"
        )
        return EDIT_SETTING

    # ── Back ──────────────────────────────────────────────────────────────────
    elif data == "adm:back":
        stats = await db.get_stats()
        text = (
            f"🔧 *Admin Panel*\n\n"
            f"👥 Total Users: *{stats['total_users']}*\n"
            f"✅ Active: *{stats['active_users']}*\n"
            f"💸 Pending Withdrawals: *{stats['pending_withdrawals']}*\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_admin_keyboard())
        return ConversationHandler.END

    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Add Task conversation steps
# ─────────────────────────────────────────────────────────────────────────────

@require_admin
async def add_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_title"] = update.message.text.strip()
    await update.message.reply_text(
        "Step 2/3 — Send the *channel/group @username* or numeric chat ID:\n\n"
        "Examples: `@MyChannel` or `-1001234567890`\n\n"
        "⚠️ The bot must be an *admin* in this channel/group to verify members.\n\n"
        "_(Type /cancel to abort)_",
        parse_mode="Markdown",
    )
    return ADD_TASK_CHAT


@require_admin
async def add_task_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text.strip()
    # Basic validation
    if not (chat_id.startswith("@") or chat_id.startswith("-") or chat_id.lstrip("-").isdigit()):
        await update.message.reply_text(
            "⚠️ Invalid format. Use `@username` or a numeric ID like `-1001234567890`.",
            parse_mode="Markdown",
        )
        return ADD_TASK_CHAT

    # Check for duplicates
    existing = await db.get_task_by_chat(chat_id)
    if existing:
        await update.message.reply_text(
            f"⚠️ A task for `{chat_id}` already exists (ID: {existing['id']}).",
            parse_mode="Markdown",
        )
        return ADD_TASK_CHAT

    context.user_data["new_task_chat"] = chat_id
    await update.message.reply_text(
        "Step 3/3 — Send the *invite link* for this channel/group:\n\n"
        "Examples: `https://t.me/MyChannel` or `https://t.me/+abcXYZ`\n\n"
        "_(Type /cancel to abort)_",
        parse_mode="Markdown",
    )
    return ADD_TASK_LINK


@require_admin
async def add_task_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith("https://t.me/"):
        await update.message.reply_text(
            "⚠️ Link must start with `https://t.me/`. Try again:",
            parse_mode="Markdown",
        )
        return ADD_TASK_LINK

    title = context.user_data.pop("new_task_title", "")
    chat_id = context.user_data.pop("new_task_chat", "")

    task = await db.add_task(title=title, chat_id=chat_id, invite_link=link)
    await update.message.reply_text(
        f"✅ *Task Added!*\n\n"
        f"📌 {task['title']}\n"
        f"Chat: `{task['chat_id']}`\n"
        f"Link: {task['invite_link']}\n\n"
        f"Users will now need to join this channel to complete tasks.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("📋 Back to Tasks", callback_data="adm:tasks")
        ]])
    )
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Broadcast conversation step
# ─────────────────────────────────────────────────────────────────────────────

@require_admin
async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message.text
    user_ids = await db.get_all_user_ids()

    status_msg = await update.message.reply_text(
        f"📢 Broadcasting to *{len(user_ids)}* users...", parse_mode="Markdown"
    )

    sent = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(uid, f"📢 *Announcement*\n\n{message}", parse_mode="Markdown")
            sent += 1
        except Exception:
            failed += 1

    await status_msg.edit_text(
        f"✅ *Broadcast Complete*\n\n"
        f"📤 Sent: {sent}\n"
        f"❌ Failed: {failed}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


@require_admin
async def edit_setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    val_str = update.message.text.strip()
    key = context.user_data.get("edit_setting_key", "")
    # Threshold fields are integers and can be 0
    is_threshold = "threshold" in key
    try:
        val = float(val_str)
        if val < 0:
            raise ValueError
        if is_threshold and not val_str.isdigit():
            raise ValueError
    except ValueError:
        hint = "a whole number like `5`" if is_threshold else "a positive number like `0.50`"
        await update.message.reply_text(
            f"⚠️ Invalid value. Must be {hint}. Try again:", parse_mode="Markdown"
        )
        return EDIT_SETTING

    key = context.user_data.pop("edit_setting_key", None)
    if key:
        await db.set_setting(key, str(int(val)) if is_threshold else str(val))
    
    display = str(int(val)) if is_threshold else fmt_balance(val)
    await update.message.reply_text(
        f"✅ *Setting Updated!*\n\nNew value: `{display}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Settings", callback_data="adm:settings")]])
    )
    return ConversationHandler.END


@require_admin
async def wreject_reason_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reason = update.message.text.strip()
    wid = context.user_data.pop("wreject_id", None)
    if not wid:
        await update.message.reply_text("❌ Error: Withdrawal ID lost.")
        return ConversationHandler.END
        
    result = await db.process_withdrawal(wid, "rejected", reject_reason=reason)
    if result:
        status_msg = (
            "❌ *Withdrawal Rejected*\n\n"
            f"Your withdrawal of {fmt_balance(result['amount'])} via {result['method']} was rejected.\n\n"
            f"Reason: *{reason}*\n\n"
            f"Your balance has been refunded."
        )
        try:
            await context.bot.send_message(result["user_id"], status_msg, parse_mode="Markdown")
        except Exception:
            pass
        await update.message.reply_text(f"✅ Withdrawal #{wid} rejected. User notified.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Withdrawals", callback_data="adm:withdrawals")]]))
    else:
        await update.message.reply_text("❌ Failed to process rejection.")
        
    return ConversationHandler.END

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _show_withdrawals(query):
    withdrawals = await db.get_pending_withdrawals()
    if not withdrawals:
        await query.edit_message_text(
            "💸 *Pending Withdrawals*\n\nNo pending withdrawals! ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]])
        )
        return

    for w in withdrawals[:5]:
        text = (
            f"💸 *Withdrawal #{w['id']}*\n\n"
            f"👤 {w['full_name']} (`{w['user_id']}`)\n"
            f"💵 Amount: {fmt_balance(w['amount'])}\n"
            f"📤 Method: {w['method']}\n"
            f"🔑 To: `{w['destination']}`\n"
            f"🕐 Requested: {w['requested_at'].strftime('%Y-%m-%d %H:%M UTC')}"
        )
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Mark Paid", callback_data=f"adm:wpay:{w['id']}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"adm:wreject:{w['id']}"),
            ]
        ])
        try:
            await query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
        except Exception:
            pass

async def _all_tasks_including_inactive():
    """Get all tasks including inactive ones for admin view."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM tasks ORDER BY position ASC, id ASC")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancel current conversation and return to the previous admin menu if possible."""
    prev_menu = context.user_data.pop("adm_prev_menu", None)
    context.user_data.clear()
    
    if prev_menu and update.message:
        # Build a fake callback-like navigation by sending an inline button
        # so the user can tap Back without having to re-type /admin
        menu_labels = {
            "adm:tasks": "⬅️ Back to Tasks",
            "adm:settings": "⬅️ Back to Settings",
            "adm:back": "⬅️ Back to Admin Panel",
        }
        # If it's a task_detail, extract the ID for the label
        if prev_menu.startswith("adm:task_detail:"):
            label = "⬅️ Back to Task"
        else:
            label = menu_labels.get(prev_menu, "⬅️ Back")
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=prev_menu)]])
        )
    elif update.message:
        await update.message.reply_text(
            "❌ Cancelled.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Admin Panel", callback_data="adm:back")]])
        )
    return ConversationHandler.END


# ─────────────────────────────────────────────────────────────────────────────
# Edit Task conversation steps
# ─────────────────────────────────────────────────────────────────────────────

@require_admin
async def edit_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.pop("edit_task_id", None)
    new_title = update.message.text.strip()
    if not new_title or not task_id:
        await update.message.reply_text("❌ Error. Try again from the task menu.")
        return ConversationHandler.END
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tasks SET title=$1 WHERE id=$2", new_title, task_id)
    await update.message.reply_text(
        f"✅ *Title updated!*\n\nNew title: `{new_title}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Task", callback_data=f"adm:task_detail:{task_id}")]])
    )
    return ConversationHandler.END


@require_admin
async def edit_task_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.pop("edit_task_id", None)
    chat_id = update.message.text.strip()
    if not task_id:
        await update.message.reply_text("❌ Error. Try again from the task menu.")
        return ConversationHandler.END
    if not (chat_id.startswith("@") or chat_id.lstrip("-").isdigit()):
        await update.message.reply_text(
            "⚠️ Invalid format. Use `@username` or a numeric ID like `-1001234567890`. Try again:",
            parse_mode="Markdown"
        )
        context.user_data["edit_task_id"] = task_id
        return EDIT_TASK_CHAT
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tasks SET chat_id=$1 WHERE id=$2", chat_id, task_id)
    await update.message.reply_text(
        f"✅ *Chat ID updated!*\n\nNew Chat ID: `{chat_id}`",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Task", callback_data=f"adm:task_detail:{task_id}")]])
    )
    return ConversationHandler.END


@require_admin
async def edit_task_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    task_id = context.user_data.pop("edit_task_id", None)
    link = update.message.text.strip()
    if not task_id:
        await update.message.reply_text("❌ Error. Try again from the task menu.")
        return ConversationHandler.END
    if not link.startswith("https://t.me/"):
        await update.message.reply_text(
            "⚠️ Link must start with `https://t.me/`. Try again:",
            parse_mode="Markdown"
        )
        context.user_data["edit_task_id"] = task_id
        return EDIT_TASK_LINK
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("UPDATE tasks SET invite_link=$1 WHERE id=$2", link, task_id)
    await update.message.reply_text(
        f"✅ *Invite link updated!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Task", callback_data=f"adm:task_detail:{task_id}")]])
    )
    return ConversationHandler.END
