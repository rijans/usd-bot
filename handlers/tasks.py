"""
handlers/tasks.py  ─  Task list + live membership verification.

User flow:
  1. Tap Tasks → see all tasks with live ✅/❌ status
  2. Tap a task → get join button
  3. Tap "✅ I Joined" → bot calls get_chat_member() to verify
  4. If verified → mark complete, check if ALL done → unlock + notify referrer
"""
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import nav_keyboard, check_all_tasks, progress_bar, fmt_balance, mask_id, clean_md

log = logging.getLogger(__name__)


async def nav_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer()
    else:
        log.info(f"User {update.effective_user.id} requested nav_tasks via reply keyboard")
    await _render_task_list(update, context)


async def _render_task_list(update: Update, context):
    """Shared task list renderer — works for both callback queries and messages."""
    query = update.callback_query
    user_id = update.effective_user.id
    tasks = await db.get_active_tasks()

    if not tasks:
        text = "📋 *Tasks*\n\nNo tasks available right now. Check back later!"
        if query:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
        else:
            await update.message.reply_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
        return

    completed_ids = await db.get_completed_task_ids(user_id)
    # Live-check membership for incomplete tasks only
    incomplete_tasks = [t for t in tasks if t["id"] not in completed_ids]
    live_status = await check_all_tasks(context.bot, user_id, incomplete_tasks)

    done = len(completed_ids)
    total = len(tasks)
    bar = progress_bar(done, total)

    text = (
        f"📋 *Tasks*  ({done}/{total} completed)\n"
        f"`{bar}`\n\n"
        f"Join the channels/groups below to unlock the bot and earn rewards!\n\n"
    )

    buttons = []
    for i, task in enumerate(tasks, 1):
        if task["id"] in completed_ids:
            status_icon = "✅"
        elif live_status.get(task["id"]):
            status_icon = "🔄"  # joined but not marked yet
        else:
            status_icon = "❌"

        reward_label = f" (+{fmt_balance(task['reward'])})" if float(task["reward"]) > 0 else ""
        label = f"{status_icon} {i}. {task['title']}{reward_label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"task:view:{task['id']}")])

    buttons.append([InlineKeyboardButton("🔄 Refresh Status", callback_data="nav:tasks")])
    markup = InlineKeyboardMarkup(buttons + [[InlineKeyboardButton("🏠 Home", callback_data="nav:start")]])

    if query:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=markup)
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=markup)


async def task_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show detail for one task with Join + Verify buttons."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    task_id = int(query.data.split(":")[2])

    task = await db.get_task(task_id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    completed_ids = await db.get_completed_task_ids(user_id)
    is_done = task_id in completed_ids
    is_joined = await check_all_tasks(context.bot, user_id, [task])
    joined_now = is_joined.get(task_id, False)

    reward_text = f"\n💰 Reward: *{fmt_balance(task['reward'])}*" if float(task["reward"]) > 0 else ""
    text = (
        f"📌 *{task['title']}*{reward_text}\n\n"
    )

    if is_done:
        text += "✅ *Already completed!*"
        buttons = [[InlineKeyboardButton("⬅️ Back to Tasks", callback_data="nav:tasks")]]
    elif joined_now:
        text += (
            "✅ You appear to be a member!\n"
            "Tap *Verify & Complete* to confirm."
        )
        buttons = [
            [InlineKeyboardButton("✅ Verify & Complete", callback_data=f"task:verify:{task_id}")],
            [InlineKeyboardButton("⬅️ Back to Tasks", callback_data="nav:tasks")],
        ]
    else:
        text += (
            "👉 Join the channel/group first, then tap *✅ I Joined* to verify."
        )
        buttons = [
            [InlineKeyboardButton("📢 Join Now", url=task["invite_link"])],
            [InlineKeyboardButton("✅ I Joined", callback_data=f"task:verify:{task_id}")],
            [InlineKeyboardButton("⬅️ Back to Tasks", callback_data="nav:tasks")],
        ]

    await query.edit_message_text(text, parse_mode="Markdown",
                                  reply_markup=InlineKeyboardMarkup(buttons))


async def task_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Verify membership and mark task complete if confirmed."""
    query = update.callback_query
    await query.answer("Verifying…")
    user_id = query.from_user.id
    task_id = int(query.data.split(":")[2])

    task = await db.get_task(task_id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    # Already done?
    completed_ids = await db.get_completed_task_ids(user_id)
    if task_id in completed_ids:
        await query.answer("Already completed!", show_alert=True)
        await _render_task_list(update, context)
        return

    # Live membership check
    membership = await check_all_tasks(context.bot, user_id, [task])
    if not membership.get(task_id):
        await query.edit_message_text(
            f"❌ *Not Verified*\n\n"
            f"We couldn't confirm your membership in *{task['title']}*.\n\n"
            f"Make sure you've joined and try again.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Now", url=task["invite_link"])],
                [InlineKeyboardButton("🔄 Try Again", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton("⬅️ Back", callback_data="nav:tasks")],
            ]),
        )
        return

    # Mark complete
    is_newly_done, task_reward = await db.mark_task_complete(user_id, task_id)
    if is_newly_done and task_reward > 0:
        try:
            await context.bot.send_message(
                user_id,
                f"🎉 You received *{fmt_balance(task_reward)}* for completing *{task['title']}*!",
                parse_mode="Markdown"
            )
        except Exception:
            pass

    just_unlocked, ref_amt = await db.check_and_finalize_tasks(user_id)

    user = await db.get_user(user_id)
    tasks = await db.get_active_tasks()
    completed_ids = await db.get_completed_task_ids(user_id)
    done = len(completed_ids)
    total = len(tasks)

    if just_unlocked:
        # Notify referrer
        if user["referred_by"] and ref_amt > 0:
            try:
                masked_name = f"User {mask_id(user_id)}"
                await context.bot.send_message(
                    user["referred_by"],
                    f"🎉 *Referral Reward!*\n\n"
                    f"Your referral *{clean_md(masked_name)}* completed all tasks!\n"
                    f"💰 *+{fmt_balance(ref_amt)}* has been added to your balance.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        # Admin Notification for milestone
        notify_admin = await db.get_setting("notify_admin_on_task_done", "1")
        if notify_admin == "1":
            try:
                admin_ids = [int(i.strip()) for i in os.environ.get("ADMIN_IDS", "").split(",") if i.strip()]
                for admin_id in admin_ids:
                    await context.bot.send_message(
                        admin_id,
                        f"🔔 *Admin Alert: Task Milestone*\n\n"
                        f"User: *{clean_md(user['full_name'])}* (`{user_id}`)\n"
                        f"Status: ✅ Completed all tasks.",
                        parse_mode="Markdown"
                    )
            except Exception:
                pass

        daily_amount = await db.get_setting("daily_bonus", "0.50")
        ref_amount = await db.get_setting("referral_reward", "0.40")

        text = (
            f"🎉 *All Tasks Completed!*\n\n"
            f"✦ You've unlocked all bot features!\n\n"
            f"What you can now do:\n"
            f"• 💰 Earn {fmt_balance(ref_amount)} per referral\n"
            f"• 🎁 Claim {fmt_balance(daily_amount)} daily bonus\n"
            f"• 💸 Withdraw at $20.00 minimum\n\n"
            f"Start by sharing your referral link!"
        )
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=nav_keyboard())
    else:
        text = (
            f"✅ *Task Verified!*\n\n"
            f"*{task['title']}* — completed!\n\n"
            f"Progress: {done}/{total} tasks done\n"
            f"{'Complete all tasks to unlock the bot! 💪' if done < total else ''}"
        )
        await query.edit_message_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Back to Tasks", callback_data="nav:tasks")]
            ]),
        )
