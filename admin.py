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
ADD_TASK_TITLE = 20
ADD_TASK_CHAT  = 21
ADD_TASK_LINK  = 22
BROADCAST_TEXT = 30


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
                [InlineKeyboardButton("🗑 Delete Task", callback_data=f"adm:delete:{task_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="adm:tasks")],
            ])
        )
        return ConversationHandler.END

    # ── Toggle task ───────────────────────────────────────────────────────────
    elif data.startswith("adm:toggle:"):
        task_id = int(data.split(":")[2])
        result = await db.toggle_task(task_id)
        state = "activated ✅" if result["active"] else "deactivated ❌"
        await query.answer(f"Task {state}!", show_alert=True)
        # Re-render task list
        context.user_data["_adm_data"] = "adm:tasks"
        query.data = "adm:tasks"
        return await admin_callback(update, context)

    # ── Delete task ───────────────────────────────────────────────────────────
    elif data.startswith("adm:delete:"):
        task_id = int(data.split(":")[2])
        ok = await db.delete_task(task_id)
        await query.answer("Deleted!" if ok else "Failed.", show_alert=True)
        query.data = "adm:tasks"
        return await admin_callback(update, context)

    # ── Add task: start ───────────────────────────────────────────────────────
    elif data == "adm:add_task":
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
        result = await db.process_withdrawal(wid, action)
        if result:
            await query.answer(f"Withdrawal {action}!", show_alert=True)
            # Notify user
            status_msg = (
                "✅ *Withdrawal Approved!*\n\nYour payment has been processed."
                if action == "paid" else
                "❌ *Withdrawal Rejected.*\n\nYour balance has been refunded."
            )
            try:
                await context.bot.send_message(result["user_id"], status_msg, parse_mode="Markdown")
            except Exception:
                pass
        await _show_withdrawals(query)
        return ConversationHandler.END

    # ── Broadcast: start ──────────────────────────────────────────────────────
    elif data == "adm:broadcast":
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Send the message to broadcast to all users.\n"
            "Supports Markdown formatting.\n\n"
            "_(Type /cancel to abort)_",
            parse_mode="Markdown",
        )
        return BROADCAST_TEXT

    # ── Stats ─────────────────────────────────────────────────────────────────
    elif data == "adm:stats":
        stats = await db.get_stats()
        top = await db.get_leaderboard(5)
        text = (
            f"📊 *Full Statistics*\n\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"✅ Active (tasks done): {stats['active_users']}\n"
            f"💰 Total Balance Owed: {fmt_balance(stats['total_balance_owed'])}\n"
            f"💸 Pending Withdrawals: {stats['pending_withdrawals']}\n\n"
            f"🏆 *Top 5 Inviters:*\n"
        )
        for i, u in enumerate(top, 1):
            text += f"{i}. {u['full_name']} — {u['total_invites']} invites\n"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]])
        )
        return ConversationHandler.END

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
    context.user_data.clear()
    if update.message:
        await update.message.reply_text("❌ Cancelled.")
    return ConversationHandler.END
