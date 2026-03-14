from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

import core.db as db
from core.ui import check_all_tasks, progress_bar, fmt_balance


async def nav_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles both callback (inline button) and message (reply keyboard)."""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        user_id = query.from_user.id
        edit_fn = query.edit_message_text
        send_fn = None
    else:
        user_id = update.effective_user.id
        edit_fn = None
        send_fn = update.message.reply_text

    await _render_task_list(user_id, context, edit_fn=edit_fn, send_fn=send_fn)


async def _render_task_list(user_id, context, edit_fn=None, send_fn=None):
    tasks = await db.get_active_tasks()

    if not tasks:
        text = (
            "📋 *Tasks*\n\n"
            "No tasks available right now.\n"
            "Check back later!"
        )
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="nav:tasks")],
            [InlineKeyboardButton("🏠 Home",    callback_data="nav:start")],
        ])
        if edit_fn:
            await edit_fn(text, parse_mode="Markdown", reply_markup=keyboard)
        elif send_fn:
            await send_fn(text, parse_mode="Markdown", reply_markup=keyboard)
        return

    completed_ids = await db.get_completed_task_ids(user_id)
    # Only live-check incomplete tasks to save API calls
    incomplete = [t for t in tasks if t["id"] not in completed_ids]
    live       = await check_all_tasks(context.bot, user_id, incomplete)

    done  = len(completed_ids)
    total = len(tasks)
    bar   = progress_bar(done, total)

    text = (
        f"📋 *Tasks*  ({done}/{total} completed)\n"
        f"`{bar}`\n\n"
        f"Join all channels below to unlock the bot!\n\n"
    )

    buttons = []
    for i, task in enumerate(tasks, 1):
        if task["id"] in completed_ids:
            icon = "✅"
        elif live.get(task["id"]) is None:
            icon = "⚠️"   # bot not admin, unverifiable
        elif live.get(task["id"]):
            icon = "🔄"   # joined but not verified yet
        else:
            icon = "❌"

        reward_label = f" +{fmt_balance(task['reward'])}" if float(task["reward"]) > 0 else ""
        label = f"{icon} {task['title']}{reward_label}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"task:view:{task['id']}")])

    buttons.append([InlineKeyboardButton("🔄 Refresh Status", callback_data="nav:tasks")])
    buttons.append([InlineKeyboardButton("🏠 Home",           callback_data="nav:start")])

    keyboard = InlineKeyboardMarkup(buttons)

    if edit_fn:
        await edit_fn(text, parse_mode="Markdown", reply_markup=keyboard)
    elif send_fn:
        await send_fn(text, parse_mode="Markdown", reply_markup=keyboard)


async def task_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    reward_text = f"\n💰 Reward: *{fmt_balance(task['reward'])}*" if float(task["reward"]) > 0 else ""
    text = f"📌 *{task['title']}*{reward_text}\n\n"

    if is_done:
        text += "✅ *Already completed!*"
        buttons = [[InlineKeyboardButton("⬅️ Back to Tasks", callback_data="nav:tasks")]]
    else:
        # Live check
        membership = await check_all_tasks(context.bot, user_id, [task])
        status = membership.get(task_id)

        if status is None:
            # Bot not admin in that chat — tell user to join and trust them
            text += (
                "⚠️ *Auto-verification unavailable*\n\n"
                "The bot cannot verify membership for this channel.\n"
                "Join the channel, then tap *Mark as Joined* to continue."
            )
            buttons = [
                [InlineKeyboardButton("📢 Join Now",       url=task["invite_link"])],
                [InlineKeyboardButton("✅ Mark as Joined", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton("⬅️ Back",           callback_data="nav:tasks")],
            ]
        elif status:
            text += "✅ You appear to be a member!\nTap *Verify & Complete* to confirm."
            buttons = [
                [InlineKeyboardButton("✅ Verify & Complete", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton("⬅️ Back to Tasks",    callback_data="nav:tasks")],
            ]
        else:
            text += "👉 Join the channel first, then tap *I Joined* to verify."
            buttons = [
                [InlineKeyboardButton("📢 Join Now", url=task["invite_link"])],
                [InlineKeyboardButton("✅ I Joined", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton("⬅️ Back",     callback_data="nav:tasks")],
            ]

    await query.edit_message_text(
        text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(buttons)
    )


async def task_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Verifying…")
    user_id = query.from_user.id
    task_id = int(query.data.split(":")[2])

    task = await db.get_task(task_id)
    if not task:
        await query.answer("Task not found.", show_alert=True)
        return

    completed_ids = await db.get_completed_task_ids(user_id)
    if task_id in completed_ids:
        await query.answer("Already completed!", show_alert=True)
        await _render_task_list(user_id, context, edit_fn=query.edit_message_text)
        return

    membership = await check_all_tasks(context.bot, user_id, [task])
    status = membership.get(task_id)

    # If bot is not admin (None), we trust the user's self-report
    if status is False:
        await query.edit_message_text(
            f"❌ *Not Verified*\n\n"
            f"We couldn't confirm your membership in *{task['title']}*.\n\n"
            f"Make sure you've joined and try again.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 Join Now",   url=task["invite_link"])],
                [InlineKeyboardButton("🔄 Try Again", callback_data=f"task:verify:{task_id}")],
                [InlineKeyboardButton("⬅️ Back",       callback_data="nav:tasks")],
            ]),
        )
        return

    # status is True or None (unverifiable) — accept both
    await db.mark_task_complete(user_id, task_id)
    just_unlocked = await db.check_and_finalize_tasks(user_id)
    user  = await db.get_user(user_id)
    tasks = await db.get_active_tasks()
    done  = len(await db.get_completed_task_ids(user_id))
    total = len(tasks)

    if just_unlocked:
        ref_reward = await db.get_setting("referral_reward")
        if user["referred_by"]:
            try:
                await context.bot.send_message(
                    user["referred_by"],
                    f"🎉 *Referral Reward!*\n\n"
                    f"Your referral *{user['full_name']}* completed all tasks!\n"
                    f"💰 *+${ref_reward}* added to your balance.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        await query.edit_message_text(
            f"🎉 *All Tasks Completed!*\n\n"
            f"✦ Bot features are now unlocked!\n\n"
            f"What you can now do:\n"
            f"• 💰 Earn ${ref_reward} per referral\n"
            f"• 🎁 Claim daily bonus\n"
            f"• 💸 Withdraw at $20.00 minimum\n\n"
            f"Start sharing your referral link!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🎯 Refer & Earn", callback_data="nav:refer")],
                [InlineKeyboardButton("🏠 Home",         callback_data="nav:start")],
            ]),
        )
    else:
        await query.edit_message_text(
            f"✅ *Task Verified!*\n\n"
            f"*{task['title']}* — completed!\n\n"
            f"Progress: {done}/{total} tasks done",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 Back to Tasks", callback_data="nav:tasks")]
            ]),
        )