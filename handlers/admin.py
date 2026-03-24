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
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, filters, MessageHandler, CommandHandler

import core.db as db
from core.ui import fmt_balance

from handlers.groups import nav_groups, group_callback
from handlers.profile import _profile_text

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
LOOKUP_USER     = 70
ADMIN_REPLY_TICKET = 80


def admin_ids() -> list[int]:
    raw = os.environ.get("ADMIN_IDS", "")
    return [int(x.strip()) for x in raw.split(",") if x.strip().isdigit()]


def require_admin(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        uid = update.effective_user.id
        if uid not in admin_ids():
            if update.message:
                await update.message.reply_text("⛔ Unauthorized.")
            elif update.callback_query:
                await update.callback_query.answer("⛔ Unauthorized.", show_alert=True)
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
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
        f"📝 Profiles Configured: *{stats.get('profiles_setup', 0)}*\n"
        f"💰 Total Balance Owed: *{fmt_balance(stats['total_balance_owed'])}*\n"
        f"💸 Pending Withdrawals: *{stats['pending_withdrawals']}*\n"
    )
    await update.message.reply_text(
        text, parse_mode="Markdown", reply_markup=_admin_keyboard()
    )


def _admin_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Manage Tasks", callback_data="adm:tasks"),
         InlineKeyboardButton("💸 Withdrawals", callback_data="adm:withdrawals")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="adm:broadcast"),
         InlineKeyboardButton("🔍 Lookup User", callback_data="adm:lookup")],
        [InlineKeyboardButton("✉️ Support Tickets", callback_data="adm:tickets"),
         InlineKeyboardButton("🎰 Lucky Draw", callback_data="adm:luckydraw")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="adm:settings"),
         InlineKeyboardButton("📈 Growth Stats", callback_data="adm:growth_stats")],
        [InlineKeyboardButton("📊 Full Stats", callback_data="adm:stats"),
         InlineKeyboardButton("📢 Promoted Groups", callback_data="adm:groups")],
    ])


# ─────────────────────────────────────────────────────────────────────────────
# Admin callbacks (entry point for ConversationHandler)
# ─────────────────────────────────────────────────────────────────────────────

import math

async def _show_paginated_users(query, page: int = 0, filter_type: str = "all"):
    per_page = 10
    total_users = await db.get_paginated_users_count(filter_type)
    total_pages = max(1, math.ceil(total_users / per_page))
    
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0
        
    offset = page * per_page
    users = await db.get_paginated_users(limit=per_page, offset=offset, filter_type=filter_type)
    
    filter_names = {
        "all": "All Users",
        "profile": "Configured Profiles",
        "referrals": "Top Referrals",
        "earnings": "Top Earners"
    }
    
    text = (
        f"🔍 *Lookup User Profile* ({filter_names.get(filter_type, 'All')})\n\n"
        f"Send the *Telegram User ID* to look up a profile directly.\n"
        f"Or click a user below:\n\n"
        f"_(Type /cancel to abort)_"
    )
    
    buttons = []
    for u in users:
        uid = u["user_id"]
        name = str(u["full_name"])[:20]
        stats_str = ""
        if filter_type == "referrals":
            stats_str = f" | {u['total_invites']} refs"
        elif filter_type == "earnings":
            stats_str = f" | {fmt_balance(u['balance'])}"
        
        # pass the page and filter in the context string so we can return here
        buttons.append([InlineKeyboardButton(f"👤 {name}{stats_str}", callback_data=f"adm:prof:{uid}")])
        
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm:ulist:{page-1}:{filter_type}"))
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm:ulist:{page+1}:{filter_type}"))
    if nav_row:
        buttons.append(nav_row)
        
    f1 = "✅ All" if filter_type == "all" else "All"
    f2 = "✅ Profile" if filter_type == "profile" else "Profile"
    f3 = "✅ Refs" if filter_type == "referrals" else "Refs"
    f4 = "✅ Earn" if filter_type == "earnings" else "Earn"
    
    buttons.append([
        InlineKeyboardButton(f1, callback_data=f"adm:ulist:0:all"),
        InlineKeyboardButton(f2, callback_data=f"adm:ulist:0:profile"),
    ])
    buttons.append([
        InlineKeyboardButton(f3, callback_data=f"adm:ulist:0:referrals"),
        InlineKeyboardButton(f4, callback_data=f"adm:ulist:0:earnings"),
    ])
    buttons.append([InlineKeyboardButton("⬅️ Back to Admin", callback_data="adm:back")])
    
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


async def _show_paginated_groups(query, context, page: int = 0):
    per_page = 10
    total_groups = await db.get_paginated_groups_count()
    total_pages = max(1, math.ceil(total_groups / per_page))
    
    if page >= total_pages: page = total_pages - 1
    if page < 0: page = 0
        
    offset = page * per_page
    groups = await db.get_paginated_groups(limit=per_page, offset=offset)
    
    text = (
        f"📢 *Promoted Telegram Groups*\n\n"
        f"Groups where the bot is added as an admin for auto-promotion.\n"
        f"Click a group to view owner details and get its invite link.\n\n"
    )
    
    buttons = []
    if not groups:
        text += "_No groups registered yet._\n"
    else:
        for g in groups:
            chat_id = g["chat_id"]
            title = (g["title"] or f"Group {chat_id}")[:25]
            owner_name = (g.get("full_name") or str(g["owner_id"]))[:15]
            status = "🟢" if g["active"] else "🔴"
            
            buttons.append([InlineKeyboardButton(f"{status} {title} | {owner_name}", callback_data=f"adm:gdetail:{chat_id}")])
            
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"adm:glist:{page-1}"))
    nav_row.append(InlineKeyboardButton(f"{page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"adm:glist:{page+1}"))
    if nav_row:
        buttons.append(nav_row)
        
    buttons.append([InlineKeyboardButton("⬅️ Back to Admin", callback_data="adm:back")])
    
    context.user_data["adm_glist_page"] = page
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))


@require_admin
async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, override_data: str = None):
    query = update.callback_query
    data = override_data or query.data

    if data == "adm:growth_stats":
        await _show_growth_stats(query)
        return ConversationHandler.END

    await query.answer()

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
        return await admin_callback(update, context, override_data=f"adm:task_detail:{task_id}")

    # ── Delete task ───────────────────────────────────────────────────────────
    elif data.startswith("adm:delete:"):
        task_id = int(data.split(":")[2])
        ok = await db.delete_task(task_id)
        await query.answer("Deleted!" if ok else "Failed.", show_alert=True)
        return await admin_callback(update, context, override_data="adm:tasks")

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

    # ── Support Tickets ───────────────────────────────────────────────────────
    elif data == "adm:tickets":
        tickets = await db.get_open_tickets(30)
        if not tickets:
            await query.edit_message_text(
                "✅ *No open tickets!* All support tickets have been handled.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]])
            )
            return ConversationHandler.END
        text = f"✉️ *Open Support Tickets* ({len(tickets)})\n\n"
        buttons = []
        for t in tickets:
            name = (t["full_name"] or "User")[:20]
            snippet = t["message"][:30].replace("\n", " ") + "…"
            buttons.append([InlineKeyboardButton(f"#{t['id']} {name}: {snippet}", callback_data=f"adm:ticket_view:{t['id']}")])
        buttons.append([InlineKeyboardButton("⬅️ Back", callback_data="adm:back")])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    elif data.startswith("adm:ticket_view:"):
        ticket_id = int(data.split(":")[2])
        ticket = await db.get_ticket(ticket_id)
        if not ticket:
            await query.answer("Ticket not found.", show_alert=True)
            return ConversationHandler.END
        name = ticket["full_name"] or "?"
        uname = f"@{ticket['username']}" if ticket["username"] else f"ID:{ticket['user_id']}"
        created = ticket["created_at"].strftime("%d %b %H:%M")
        text = (
            f"✉️ *Ticket #{ticket['id']}*\n"
            f"From: {name} ({uname})\n"
            f"Date: {created}\n"
            f"Status: {ticket['status']}\n\n"
            f"💬 *Message:*\n{ticket['message']}"
        )
        if ticket["reply"]:
            text += f"\n\n↩️ *Admin reply:*\n{ticket['reply']}"
        buttons = [
            [InlineKeyboardButton("↩️ Reply", callback_data=f"adm:ticket_reply:{ticket_id}"),
             InlineKeyboardButton("✅ Mark Solved", callback_data=f"adm:ticket_close:{ticket_id}")],
            [InlineKeyboardButton("⬅️ Back to Tickets", callback_data="adm:tickets")],
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    elif data.startswith("adm:ticket_close:"):
        ticket_id = int(data.split(":")[2])
        await db.close_ticket(ticket_id)
        await query.answer("✅ Ticket closed!", show_alert=True)
        return await admin_callback(update, context, override_data="adm:tickets")

    elif data.startswith("adm:ticket_reply:"):
        ticket_id = int(data.split(":")[2])
        context.user_data["reply_ticket_id"] = ticket_id
        await query.edit_message_text(
            f"↩️ *Reply to Ticket #{ticket_id}*\n\nType your reply message below.\n\n_(Type /cancel to abort)_",
            parse_mode="Markdown"
        )
        return ADMIN_REPLY_TICKET

    # ── Lookup User ───────────────────────────────────────────────────────────
    elif data == "adm:lookup":
        context.user_data["adm_prev_menu"] = "adm:lookup"
        await _show_paginated_users(query, page=0, filter_type="all")
        return LOOKUP_USER
        
    # ── Promoted Groups ───────────────────────────────────────────────────────
    elif data == "adm:groups":
        await _show_paginated_groups(query, context, page=0)
        return ConversationHandler.END
        
    elif data.startswith("adm:glist:"):
        page = int(data.split(":")[2])
        await _show_paginated_groups(query, context, page)
        return ConversationHandler.END
        
    elif data.startswith("adm:gdetail:"):
        chat_id = int(data.split(":")[2])
        group = await db.get_group(chat_id)
        if not group:
            await query.answer("Group not found in database.", show_alert=True)
            return ConversationHandler.END
            
        owner = await db.get_user(group["owner_id"])
        owner_name = owner["full_name"] if owner else str(group["owner_id"])
        
        # Try to dynamically get invite link
        link = "Not available"
        try:
            link = await context.bot.export_chat_invite_link(chat_id)
        except Exception as e:
            link = f"Bot lacks invite permissions."
            
        status = "🟢 Active" if group["active"] else "🔴 Paused"
        interval = f"{group['interval_hours']} hours"
        
        text = (
            f"📢 *Group Detail*\n\n"
            f"🏷 *Title:* {group['title'] or 'Unknown'}\n"
            f"🆔 *Chat ID:* `{chat_id}`\n"
            f"🔗 *Invite Link:* {link}\n\n"
            f"👤 *Owner:* {owner_name}\n"
            f"🆔 *Owner ID:* `{group['owner_id']}`\n\n"
            f"⚙️ *Settings:*\n"
            f"Status: {status}\n"
            f"Interval: {interval}\n"
        )
        
        page = context.user_data.get("adm_glist_page", 0)
        buttons = [
            [InlineKeyboardButton("⬅️ Back to Groups", callback_data=f"adm:glist:{page}")]
        ]
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons))
        return ConversationHandler.END

    # ── Lookup User List Pagination ──────────────────────────────────────────
    elif data.startswith("adm:ulist:"):
        parts = data.split(":")
        page = int(parts[2])
        filter_type = parts[3]
        context.user_data["adm_prev_menu"] = data
        await _show_paginated_users(query, page=page, filter_type=filter_type)
        return LOOKUP_USER

    # ── View Profile (read-only) ──────────────────────────────────────────────
    elif data.startswith("adm:prof:"):
        uid = int(data.split(":")[2])
        user = await db.get_user(uid)
        profile = await db.get_profile(uid)
        if not user:
            await query.answer("User not found.", show_alert=True)
            return ConversationHandler.END

        text = _profile_text(user, profile)
        
        # Determine back button based on context
        prev = context.user_data.get("adm_prev_menu", "adm:withdrawals")
        if data.endswith("_lookup"):
            # if we came from lookup user, back goes to admin menu
            prev = "adm:back"
            
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data=prev)]])
        )
        return ConversationHandler.END


    # ── Full Stats ────────────────────────────────────────────────────────────
    elif data == "adm:stats":
        stats = await db.get_stats()
        top_inviters = await db.get_leaderboard(10, include_fake=False)
        top_earners = await db.get_earners_leaderboard(10, include_fake=False)
        
        text = (
            f"📊 *Full Statistics*\n\n"
            f"👥 Total Users: {stats['total_users']}\n"
            f"✅ Active (tasks done): {stats['active_users']}\n"
            f"📝 Profiles Configured: {stats.get('profiles_setup', 0)}\n"
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
        
        notify_admin = await db.get_setting("notify_admin_on_task_done", "1")
        notify_label = "🔔 Admin Alerts: ON" if notify_admin == "1" else "🔕 Admin Alerts: OFF"

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
            [InlineKeyboardButton(notify_label, callback_data="adm:toggle_admin_notify")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return ConversationHandler.END

    elif data == "adm:toggle_admin_notify":
        current = await db.get_setting("notify_admin_on_task_done", "1")
        new_val = "0" if current == "1" else "1"
        await db.set_setting("notify_admin_on_task_done", new_val)
        await query.answer(f"Admin alerts {'enabled' if new_val == '1' else 'disabled'}!")
        return await admin_callback(update, context, override_data="adm:settings")

    elif data == "adm:luckydraw":
        stats = await db.get_lucky_draw_admin_stats()
        p1 = await db.get_setting("ld_prize_1", "200")
        p2 = await db.get_setting("ld_prize_2", "70")
        p3 = await db.get_setting("ld_prize_3", "30")
        text = (
            f"🎰 *Lucky Draw Admin Panel*\n\n"
            f"📅 *Today's Entries:* {stats['today_entries']}\n"
            f"⭐️ *Stars Collected Today:* {stats['today_stars']}\n\n"
            f"📊 *All Time:*\n"
            f"  Total entries: {stats['total_entries']}\n"
            f"  Total stars: {stats['total_stars']}\n"
            f"  Unique buyers: {stats['unique_buyers']}\n\n"
            f"🏆 *Current Prizes:*\n"
            f"  🥇 1st Place: ${p1} USD\n"
            f"  🥈 2nd Place: ${p2} USD\n"
            f"  🥉 3rd Place: ${p3} USD"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📜 Buyer History (Last 20)", callback_data="adm:ld_history")],
            [InlineKeyboardButton("✏️ Edit 1st Prize ($)", callback_data="adm:edit_set:ld_prize_1"),
             InlineKeyboardButton("✏️ Edit 2nd Prize ($)", callback_data="adm:edit_set:ld_prize_2")],
            [InlineKeyboardButton("✏️ Edit 3rd Prize ($)", callback_data="adm:edit_set:ld_prize_3")],
            [InlineKeyboardButton("⬅️ Back", callback_data="adm:back")],
        ])
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
        return ConversationHandler.END

    elif data == "adm:ld_history":
        history = await db.get_lucky_draw_entry_history(limit=20)
        if not history:
            text = "🎰 *Lucky Draw Buyer History*\n\n_No entries recorded yet._"
        else:
            text = "🎰 *Lucky Draw Buyer History (Last 20)*\n\n"
            for row in history:
                name = row['full_name'] or row['username'] or str(row['user_id'])
                date_str = row['draw_date'].strftime("%b %d")
                text += f"⭐ {row['stars_paid']} | {name} | {date_str}\n"
        await query.edit_message_text(
            text, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:luckydraw")]])
        )
        return ConversationHandler.END

    elif data == "adm:toggle_fake":
        current = await db.get_setting("show_fake_leaders", "1")
        new_val = "0" if current == "1" else "1"
        await db.set_setting("show_fake_leaders", new_val)
        await query.answer(f"Fake leaders {'enabled' if new_val == '1' else 'disabled'}!")
        return await admin_callback(update, context, override_data="adm:settings")

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
            "ld_prize_1": "Lucky Draw 1st Prize (USD)",
            "ld_prize_2": "Lucky Draw 2nd Prize (USD)",
            "ld_prize_3": "Lucky Draw 3rd Prize (USD)",
        }
        # Show current value
        defaults = {
            "signup_bonus": "1.00", "task_reward": "0.30",
            "daily_bonus_primary": "0.20", "daily_bonus_secondary": "0.02",
            "daily_bonus_threshold": "5", "referral_reward_primary": "0.30",
            "referral_reward_secondary": "0.05", "referral_reward_threshold": "5",
            "ld_prize_1": "200", "ld_prize_2": "70", "ld_prize_3": "30",
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
            f"📝 Profiles Configured: *{stats.get('profiles_setup', 0)}*\n"
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


@require_admin
async def lookup_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id_str = update.message.text.strip()
    if not user_id_str.isdigit():
        await update.message.reply_text("⚠️ User ID must be a number. Try again or /cancel:")
        return LOOKUP_USER
        
    uid = int(user_id_str)
    user = await db.get_user(uid)
    if not user:
        await update.message.reply_text("❌ User not found. Try another ID or /cancel:")
        return LOOKUP_USER
        
    profile = await db.get_profile(uid)
    text = _profile_text(user, profile)
    await update.message.reply_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin Panel", callback_data="adm:back")]])
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
            ],
            [InlineKeyboardButton("👤 View Profile", callback_data=f"adm:prof:{w['user_id']}")]
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


# ── Balance Adjustments ───────────────────────────────────────────────────────

@require_admin
async def cmd_addbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: `/addbalance <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        user_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        if not user:
            await update.message.reply_text("User not found.")
            return
        await db.add_balance(user_id, amount, conn)
        # Record transaction for history
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type) VALUES ($1, $2, 'admin_bonus')",
            user_id, amount
        )
        new_user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)

    await update.message.reply_text(f"✅ Added *${amount:.2f}* to user {user_id}.\nNew balance: *${new_user['balance']:.2f}*", parse_mode="Markdown")


@require_admin
async def cmd_deductbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: `/deductbalance <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        user_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        if not user:
            await update.message.reply_text("User not found.")
            return
        await db.add_balance(user_id, -amount, conn)
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type) VALUES ($1, $2, 'admin_deduct')",
            user_id, -amount
        )
        new_user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)

    await update.message.reply_text(f"✅ Deducted *${amount:.2f}* from user {user_id}.\nNew balance: *${new_user['balance']:.2f}*", parse_mode="Markdown")


@require_admin
async def cmd_setbalance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Usage: `/setbalance <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        user_id = int(args[0])
        amount = float(args[1])
    except ValueError:
        await update.message.reply_text("Invalid arguments.")
        return

    pool = await db.get_pool()
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)
        if not user:
            await update.message.reply_text("User not found.")
            return
            
        old_balance = user['balance']
        diff = amount - float(old_balance)
        
        await conn.execute("UPDATE users SET balance=$2 WHERE user_id=$1", user_id, amount)
        await conn.execute(
            "INSERT INTO transactions (user_id, amount, type) VALUES ($1, $2, 'admin_set')",
            user_id, diff
        )
        new_user = await conn.fetchrow("SELECT balance FROM users WHERE user_id=$1", user_id)

    await update.message.reply_text(f"✅ Set balance of user {user_id} to *${amount:.2f}*.\nOld balance: *${old_balance:.2f}*", parse_mode="Markdown")


# ── Reply to Ticket ───────────────────────────────────────────────────────────

@require_admin
async def admin_ticket_reply_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ticket_id = context.user_data.get("reply_ticket_id")
    if not ticket_id:
        await update.message.reply_text("No active ticket reply session. Type /cancel to abort.")
        return ADMIN_REPLY_TICKET

    text = update.message.text.strip()
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        await update.message.reply_text("Ticket no longer exists.")
        return ConversationHandler.END

    await db.reply_ticket(ticket_id, text)
    
    # Notify user
    try:
        await context.bot.send_message(
            chat_id=ticket["user_id"],
            text=f"✉️ *Support Ticket Update*\n\nYour ticket #{ticket_id} has received a reply from an admin!\n\n💬 *Admin:* {text}\n\n_To check your tickets, visit FAQ & Support -> My Ticket Status._",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"⚠️ Marked as answered, but failed to notify user: `{str(e)}`", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"✅ Reply sent to user for Ticket #{ticket_id}!")

    # Return to tickets view
    class FakeQuery:
        data = "adm:tickets"
        from_user = update.message.from_user
        async def answer(self, *args, **kwargs): pass
        async def edit_message_text(self, text, **kwargs):
            await update.message.reply_text(text, **kwargs)
            
    class FakeUpdate:
        callback_query = FakeQuery()
        effective_user = update.effective_user

    return await admin_callback(FakeUpdate(), context)

async def _show_growth_stats(query):
    stats = await db.get_growth_stats(days=14)
    joins = stats["joins"]
    tasks = stats["tasks"]
    
    # Generate a sorted list of last 14 days
    today = datetime.now().date()
    days = [(today - timedelta(days=i)) for i in range(13, -1, -1)]
    
    lines = ["📈 *Growth Stats (Last 14 Days)*\n"]
    lines.append("`Date   | Joins | Tasks`")
    lines.append("`-----------------------`")
    
    total_j = total_t = 0
    for d in days:
        j_count = joins.get(d, 0)
        t_count = tasks.get(d, 0)
        total_j += j_count
        total_t += t_count
        
        date_str = d.strftime("%b %d")
        lines.append(f"`{date_str} | {j_count:5} | {t_count:5}`")
        
    lines.append("`-----------------------`")
    lines.append(f"`TOTAL  | {total_j:5} | {total_t:5}`")
    
    text = "\n".join(lines)
    text += (
        "\n\n*Activity Summary:*\n"
        f"👥 New Users: *{total_j}*\n"
        f"✅ Tasks Done: *{total_t}*\n"
    )
    
    await query.edit_message_text(
        text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data="adm:back")]])
    )
