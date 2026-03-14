import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

import core.db as db
from core.ui import fmt_balance

ADD_TASK_TITLE   = 20
ADD_TASK_CHAT    = 21
ADD_TASK_LINK    = 22
BROADCAST_TEXT   = 30
EDIT_SETTING_VAL = 40


def admin_ids() -> list:
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


def _admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Manage Tasks",   callback_data="adm:tasks")],
        [InlineKeyboardButton("⚙️ Bot Settings",   callback_data="adm:settings")],
        [InlineKeyboardButton("💸 Withdrawals",    callback_data="adm:withdrawals")],
        [InlineKeyboardButton("📢 Broadcast",      callback_data="adm:broadcast")],
        [InlineKeyboardButton("📊 Full Stats",     callback_data="adm:stats")],
    ])


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
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=_admin_keyboard())


@require_admin
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # ── Task list ─────────────────────────────────────────────────────────────
    if data == "adm:tasks":
        all_tasks = await _get_all_tasks()
        active_count = sum(1 for t in all_tasks if t["active"])
        text = f"📋 *Tasks* ({active_count} active / {len(all_tasks)} total)\n\n"
        buttons = []
        for t in all_tasks:
            icon = "✅" if t["active"] else "❌"
            buttons.append([InlineKeyboardButton(
                f"{icon} {t['title']}",
                callback_data=f"adm:task_detail:{t['id']}"
            )])
        buttons.append([InlineKeyboardButton("➕ Add New Task", callback_data="adm:add_task")])
        buttons.append([InlineKeyboardButton("⬅️ Back",        callback_data="adm:back")])
        await query.edit_message_text(text, parse_mode="Markdown",
                                      reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    # ── Task detail ───────────────────────────────────────────────────────────
    elif data.startswith("adm:task_detail:"):
        task_id = int(data.split(":")[2])
        task    = await db.get_task(task_id)
        if not task:
            await query.answer("Not found.", show_alert=True)
            return ConversationHandler.END
        status = "✅ Active" if task["active"] else "❌ Inactive"
        text = (
            f"📌 *{task['title']}*\n\n"
            f"Chat ID: `{task['chat_id']}`\n"
            f"Link: {task['invite_link']}\n"
            f"Reward: {fmt_balance(task['reward'])}\n"
            f"Status: {status}"
        )
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Toggle Active/Inactive", callback_data=f"adm:toggle:{task_id}")],
                [InlineKeyboardButton("🗑 Delete Task",            callback_data=f"adm:delete:{task_id}")],
                [InlineKeyboardButton("⬅️ Back",                   callback_data="adm:tasks")],
            ])
        )
        return ConversationHandler.END

    # ── Toggle / delete task ──────────────────────────────────────────────────
    elif data.startswith("adm:toggle:"):
        task_id = int(data.split(":")[2])
        result  = await db.toggle_task(task_id)
        state   = "activated ✅" if result["active"] else "deactivated ❌"
        await query.answer(f"Task {state}!", show_alert=True)
        query.data = "adm:tasks"
        return await admin_callback(update, context)

    elif data.startswith("adm:delete:"):
        task_id = int(data.split(":")[2])
        ok = await db.delete_task(task_id)
        await query.answer("Deleted!" if ok else "Failed.", show_alert=True)
        query.data = "adm:tasks"
        return await admin_callback(update, context)

    # ── Add task: start ───────────────────────────────────────────────────────
    elif data == "adm:add_task":
        await query.edit_message_text(
            "📋 *Add New Task* — Step 1/3\n\n"
            "Send the *task title*\n"
            "Example: `Join Our Announcement Channel`\n\n"
            "_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return ADD_TASK_TITLE

    # ── Settings ──────────────────────────────────────────────────────────────
    elif data == "adm:settings":
        await _show_settings(query)
        return ConversationHandler.END

    elif data.startswith("adm:edit_setting:"):
        key = data.split(":", 2)[2]
        context.user_data["edit_setting_key"] = key
        labels = {
            "referral_reward":      "Referral Reward ($)",
            "daily_reward":         "Daily Bonus ($)",
            "min_withdraw":         "Minimum Withdrawal ($)",
            "withdraw_cooldown_days": "Withdrawal Cooldown (days)",
        }
        current = await db.get_setting(key)
        await query.edit_message_text(
            f"⚙️ *Edit Setting: {labels.get(key, key)}*\n\n"
            f"Current value: *{current}*\n\n"
            f"Send the new value (numbers only):\n\n"
            f"_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return EDIT_SETTING_VAL

    # ── Withdrawals ───────────────────────────────────────────────────────────
    elif data == "adm:withdrawals":
        await _show_withdrawals(query, context)
        return ConversationHandler.END

    elif data.startswith("adm:wpay:") or data.startswith("adm:wreject:"):
        action = "paid" if data.startswith("adm:wpay:") else "rejected"
        wid    = int(data.split(":")[2])
        result = await db.process_withdrawal(wid, action)
        if result:
            await query.answer(f"Withdrawal {action}!", show_alert=True)
            msg = (
                "✅ *Withdrawal Approved!*\n\nYour payment has been processed."
                if action == "paid" else
                "❌ *Withdrawal Rejected.*\n\nYour balance has been refunded."
            )
            try:
                await context.bot.send_message(result["user_id"], msg, parse_mode="Markdown")
            except Exception:
                pass
        await _show_withdrawals(query, context)
        return ConversationHandler.END

    # ── Broadcast: start ──────────────────────────────────────────────────────
    elif data == "adm:broadcast":
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Send the message to broadcast to ALL users.\n"
            "Supports Markdown formatting.\n\n"
            "_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return BROADCAST_TEXT

    # ── Full stats ────────────────────────────────────────────────────────────
    elif data == "adm:stats":
        stats = await db.get_stats()
        text  = (
            f"📊 *Full Statistics*\n\n"
            f"👥 Total Users: *{stats['total_users']}*\n"
            f"✅ Active (tasks done): *{stats['active_users']}*\n"
            f"💰 Total Balance Owed: *{fmt_balance(stats['total_balance_owed'])}*\n"
            f"💸 Pending Withdrawals: *{stats['pending_withdrawals']}*\n\n"
            f"🏆 *Top 10 Inviters:*\n"
        )
        for i, u in enumerate(stats["top_inviters"], 1):
            name  = (u["full_name"] or "User")[:18]
            text += f"{i}. {name} — *{u['total_invites']} invites*\n"

        text += f"\n💰 *Top 10 Earners:*\n"
        for i, u in enumerate(stats["top_earners"], 1):
            name  = (u["full_name"] or "User")[:18]
            text += f"{i}. {name} — *{fmt_balance(u['balance'])}*\n"

        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]
            ])
        )
        return ConversationHandler.END

    # ── Back ──────────────────────────────────────────────────────────────────
    elif data == "adm:back":
        stats = await db.get_stats()
        text  = (
            f"🔧 *Admin Panel*\n\n"
            f"👥 Total Users: *{stats['total_users']}*\n"
            f"✅ Active: *{stats['active_users']}*\n"
            f"💸 Pending Withdrawals: *{stats['pending_withdrawals']}*\n"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=_admin_keyboard())
        return ConversationHandler.END

    return ConversationHandler.END


# ── Add task conversation steps ───────────────────────────────────────────────

@require_admin
async def add_task_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_task_title"] = update.message.text.strip()
    await update.message.reply_text(
        "📋 *Add New Task* — Step 2/3\n\n"
        "Send the channel/group *@username* or numeric chat ID:\n\n"
        "Examples:\n`@MyChannel`\n`-1001234567890`\n\n"
        "⚠️ Bot must be *admin* in this channel to verify members.\n\n"
        "_(Type /cancel to abort)_",
        parse_mode="Markdown",
    )
    return ADD_TASK_CHAT


@require_admin
async def add_task_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.message.text.strip()
    if not (chat_id.startswith("@") or chat_id.lstrip("-").isdigit()):
        await update.message.reply_text(
            "⚠️ Invalid format. Use `@username` or a numeric ID.", parse_mode="Markdown"
        )
        return ADD_TASK_CHAT

    existing = await db.get_task_by_chat(chat_id)
    if existing:
        await update.message.reply_text(
            f"⚠️ A task for `{chat_id}` already exists (ID: {existing['id']}).",
            parse_mode="Markdown"
        )
        return ADD_TASK_CHAT

    context.user_data["new_task_chat"] = chat_id
    await update.message.reply_text(
        "📋 *Add New Task* — Step 3/3\n\n"
        "Send the *invite link*:\n\n"
        "Examples:\n`https://t.me/MyChannel`\n`https://t.me/+abcXYZ`\n\n"
        "_(Type /cancel to abort)_",
        parse_mode="Markdown",
    )
    return ADD_TASK_LINK


@require_admin
async def add_task_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    link = update.message.text.strip()
    if not link.startswith("https://t.me/"):
        await update.message.reply_text(
            "⚠️ Link must start with `https://t.me/`. Try again:", parse_mode="Markdown"
        )
        return ADD_TASK_LINK

    title   = context.user_data.pop("new_task_title", "")
    chat_id = context.user_data.pop("new_task_chat", "")
    task    = await db.add_task(title=title, chat_id=chat_id, invite_link=link)

    await update.message.reply_text(
        f"✅ *Task Added!*\n\n"
        f"📌 {task['title']}\n"
        f"Chat: `{task['chat_id']}`\n"
        f"Link: {task['invite_link']}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📋 Back to Tasks", callback_data="adm:tasks")]
        ])
    )
    return ConversationHandler.END


# ── Settings conversation step ────────────────────────────────────────────────

@require_admin
async def edit_setting_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key   = context.user_data.pop("edit_setting_key", None)
    value = update.message.text.strip()

    if not key:
        return ConversationHandler.END

    try:
        float(value)  # Validate it's a number
    except ValueError:
        await update.message.reply_text(
            "⚠️ Invalid value. Please send a number (e.g. `0.40` or `15`).",
            parse_mode="Markdown"
        )
        context.user_data["edit_setting_key"] = key
        return EDIT_SETTING_VAL

    await db.set_setting(key, value)
    labels = {
        "referral_reward":        "Referral Reward",
        "daily_reward":           "Daily Bonus",
        "min_withdraw":           "Minimum Withdrawal",
        "withdraw_cooldown_days": "Withdrawal Cooldown",
    }
    await update.message.reply_text(
        f"✅ *{labels.get(key, key)}* updated to *{value}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⚙️ Back to Settings", callback_data="adm:settings")]
        ])
    )
    return ConversationHandler.END


# ── Broadcast conversation step ───────────────────────────────────────────────

@require_admin
async def broadcast_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message  = update.message.text
    user_ids = await db.get_all_user_ids()
    status   = await update.message.reply_text(
        f"📢 Broadcasting to *{len(user_ids)}* users...", parse_mode="Markdown"
    )
    sent = failed = 0
    for uid in user_ids:
        try:
            await context.bot.send_message(
                uid, f"📢 *Announcement*\n\n{message}", parse_mode="Markdown"
            )
            sent += 1
        except Exception:
            failed += 1

    await status.edit_text(
        f"✅ *Broadcast Complete*\n\n📤 Sent: {sent}\n❌ Failed: {failed}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _show_settings(query):
    settings = await db.get_all_settings()
    labels   = {
        "referral_reward":        ("💵 Referral Reward",       "$"),
        "daily_reward":           ("🎁 Daily Bonus",           "$"),
        "min_withdraw":           ("💸 Min Withdrawal",        "$"),
        "withdraw_cooldown_days": ("⏳ Withdraw Cooldown",     " days"),
    }
    text = "⚙️ *Bot Settings*\n\n"
    for key, (label, unit) in labels.items():
        val   = settings.get(key, "—")
        text += f"{label}: *{val}{unit}*\n"

    buttons = [
        [InlineKeyboardButton(f"Edit {labels[k][0]}", callback_data=f"adm:edit_setting:{k}")]
        for k in labels if k in settings
    ]
    buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="adm:back")])
    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def _show_withdrawals(query, context):
    withdrawals = await db.get_pending_withdrawals()
    if not withdrawals:
        await query.edit_message_text(
            "💸 *Pending Withdrawals*\n\nNo pending withdrawals! ✅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]
            ])
        )
        return

    await query.edit_message_text(
        f"💸 *Pending Withdrawals* ({len(withdrawals)} total)\n\nSee requests below:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]
        ])
    )

    for w in withdrawals[:5]:
        text = (
            f"💸 *Withdrawal #{w['id']}*\n\n"
            f"👤 {w['full_name']} (`{w['user_id']}`)\n"
            f"💵 Amount: {fmt_balance(w['amount'])}\n"
            f"📤 Method: {w['method']}\n"
            f"🔑 To: `{w['destination']}`\n"
            f"🕐 {w['requested_at'].strftime('%Y-%m-%d %H:%M UTC')}"
        )
        try:
            await context.bot.send_message(
                query.from_user.id, text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Mark Paid",   callback_data=f"adm:wpay:{w['id']}"),
                        InlineKeyboardButton("❌ Reject",       callback_data=f"adm:wreject:{w['id']}"),
                    ]
                ])
            )
        except Exception:
            pass


async def _get_all_tasks():
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM tasks ORDER BY position ASC, id ASC")


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END