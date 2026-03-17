import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

import core.db as db
from handlers.start    import cmd_start, nav_start
from handlers.tasks    import nav_tasks, task_view, task_verify
from handlers.earnings import nav_earnings, claim_daily, show_leaderboard, nav_history
from handlers.referral import nav_share, nav_refer
from handlers.withdraw import (
    nav_withdraw, pick_method, enter_destination, cancel_withdraw,
    PICK_METHOD, ENTER_DEST,
)
from handlers.admin import (
    cmd_admin, admin_callback, cancel, edit_setting_value,
    add_task_title, add_task_chat, add_task_link,
    edit_task_title, edit_task_chat, edit_task_link,
    broadcast_text, wreject_reason_text,
    ADD_TASK_TITLE, ADD_TASK_CHAT, ADD_TASK_LINK,
    BROADCAST_TEXT, EDIT_SETTING, WREJECT_REASON,
    EDIT_TASK_TITLE, EDIT_TASK_CHAT, EDIT_TASK_LINK,
    admin_ids
)
from handlers.groups import nav_groups, group_callback

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def daily_bonus_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id FROM users WHERE user_id > 0 AND (last_daily IS NULL OR last_daily < CURRENT_DATE)")
        msg = "🎁 *Your daily bonus is ready!*\n\nClaim it now from the 💰 Earnings menu! (Requires 2 invites this week to activate)"
        for u in users:
            try:
                await context.bot.send_message(u["user_id"], msg, parse_mode="Markdown")
                import asyncio
                await asyncio.sleep(0.05) # Safe rate limit: 20 msgs per sec
            except Exception:
                pass

async def test_daily_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in admin_ids():
        return
    await update.message.reply_text("Triggering test daily broadcast...")
    await daily_bonus_reminder(context)
    await update.message.reply_text("Broadcast complete.")


async def on_bot_added(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when the bot joins a group — register the group for the user who added it."""
    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            # The user who added the bot
            adder = update.effective_user
            chat = update.effective_chat
            if not adder:
                return
            # Make sure adder is in our users table first
            user = await db.get_user(adder.id)
            if not user:
                return  # Bot was added by a non-registered user; skip
            title = chat.title or f"Group {chat.id}"
            await db.upsert_group(chat.id, title, adder.id)
            log.info(f"Group {chat.id} ({title}) registered by user {adder.id}")
            try:
                await context.bot.send_message(
                    adder.id,
                    f"✅ *Bot added to group!*\n\n"
                    f"Your group *{title}* is now registered.\n"
                    f"The bot will automatically post your referral link in the group."
                    f"\n\nTap *📢 My Groups* in your private chat to configure the posting interval.",
                    parse_mode="Markdown",
                )
            except Exception:
                pass


async def on_bot_removed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Called when the bot is kicked from a group — remove its registration."""
    if update.message.left_chat_member and update.message.left_chat_member.id == context.bot.id:
        chat_id = update.effective_chat.id
        await db.delete_group(chat_id)
        log.info(f"Group {chat_id} removed (bot was kicked)")


async def auto_promote_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Runs every 5 minutes. Posts referral links in due groups."""
    import asyncio
    from core.ui import invite_link as build_invite_link, BOT_USERNAME
    groups = await db.get_groups_due_for_promotion()
    for g in groups:
        owner_id = g["owner_id"]
        link = build_invite_link(owner_id)
        text = (
            f"💰 *Earn Real Money on Telegram!*\n\n"
            f"Join using the link below and start earning immediately:"
            f"\n\n🔗 {link}\n\n"
            f"✅ Get ${'{:.2f}'.format(1.00)} welcome bonus\n"
            f"📋 Complete simple tasks\n"
            f"👥 Invite friends & earn more\n"
            f"💸 Withdraw via TON, USDT, PayPal & more"
        )
        try:
            await context.bot.send_message(g["chat_id"], text, parse_mode="Markdown")
            await db.mark_group_posted(g["chat_id"])
        except Exception as e:
            log.warning(f"Failed to post to group {g['chat_id']}: {e}")
            # If bot kicked or group deleted, clean up
            err_str = str(e).lower()
            if "kicked" in err_str or "chat not found" in err_str or "bot was blocked" in err_str:
                await db.delete_group(g["chat_id"])
        await asyncio.sleep(0.1)  # avoid rate limits


async def post_init(application: Application) -> None:
    await db.init_schema()
    log.info("DB schema ready.")
    
    # Schedule daily bonus reminder at 10:00 UTC
    import datetime
    t = datetime.time(hour=10, minute=0, tzinfo=datetime.timezone.utc)
    application.job_queue.run_daily(daily_bonus_reminder, t)
    log.info(f"Daily job scheduled at {t} UTC")

    # Schedule group auto-promotion check every 5 minutes
    application.job_queue.run_repeating(auto_promote_job, interval=300, first=60)
    log.info("Group auto-promoter job scheduled (every 5 min)")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, BadRequest) and "Message is not modified" in str(err):
        return
        
    if isinstance(err, Conflict):
        log.warning("Conflict error detected - this is normal during bot restart/deployment.")
        return
    
    log.error("Unhandled exception", exc_info=err)
    
    # Notify admins
    import traceback
    admin_ids = os.environ.get("ADMIN_IDS", "")
    if admin_ids:
        admins = [int(x.strip()) for x in admin_ids.split(",") if x.strip().isdigit()]
        tb_str = "".join(traceback.format_exception(None, err, err.__traceback__))
        err_msg = f"❌ *Unhandled Exception*\n\n`{tb_str[-1000:]}`" # Sent last 1000 chars of traceback
        for admin_id in admins:
            try:
                await context.bot.send_message(admin_id, err_msg, parse_mode="Markdown")
            except Exception:
                pass


# ── Slash command shortcuts ───────────────────────────────────────────────────
# These open the inline panel for each section via a small bridge message.

def _open_button(label: str, callback: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=callback)]])


async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_tasks(update, context)

async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_earnings(update, context)

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_refer(update, context)

async def cmd_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_share(update, context)


# ── Reply keyboard button handler ────────────────────────────────────────────
# Handles the persistent bottom keyboard button taps.
# Each button sends its label as plain text — we match and route it.

async def reply_kb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "🏠 Home":
        await nav_start(update, context)
    elif text == "📋 Tasks":
        await nav_tasks(update, context)
    elif text == "💰 Earnings":
        await nav_earnings(update, context)
    elif text == "📤 Share":
        await nav_share(update, context)
    elif text == "👥 Refer":
        await nav_refer(update, context)
    elif text == "💸 Withdraw":
        await nav_withdraw(update, context)

async def cmd_reseed_fake(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in admin_ids():
        return
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM users WHERE user_id < 0")
    await db.init_schema()
    await update.message.reply_text("✅ Fake users reseeded with new diverse names and higher stats!")

def main():
    token = os.environ["BOT_TOKEN"]

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    app.add_error_handler(error_handler)

    # ── Slash commands ────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",    cmd_start))
    app.add_handler(CommandHandler("tasks",    cmd_tasks))
    app.add_handler(CommandHandler("earnings", cmd_earnings))
    app.add_handler(CommandHandler("refer",    cmd_refer))
    app.add_handler(CommandHandler("share",    cmd_share))
    app.add_handler(CommandHandler("reseed_fake", cmd_reseed_fake))
    app.add_handler(CommandHandler("test_daily_job", test_daily_job))
    app.add_handler(CommandHandler("mygroups", nav_groups))

    # ── Inline nav buttons ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_start,    pattern="^nav:start$"))
    app.add_handler(CallbackQueryHandler(nav_tasks,    pattern="^nav:tasks$"))
    app.add_handler(CallbackQueryHandler(nav_share,    pattern="^nav:share$"))
    app.add_handler(CallbackQueryHandler(nav_earnings, pattern="^nav:earnings$"))
    app.add_handler(CallbackQueryHandler(nav_refer,    pattern="^nav:refer$"))

    # ── Group callback ────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_groups,     pattern="^nav:groups$"))
    app.add_handler(CallbackQueryHandler(group_callback, pattern="^grp:"))

    # ── Group status update handlers ──────────────────────────────────────────
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added))
    app.add_handler(MessageHandler(filters.StatusUpdate.LEFT_CHAT_MEMBER, on_bot_removed))

    # ── Task callbacks ────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(task_view,   pattern="^task:view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(task_verify, pattern="^task:verify:[0-9]+$"))

    # ── Earnings callbacks ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(claim_daily,      pattern="^earnings:daily$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^earnings:leaderboard$"))
    app.add_handler(CallbackQueryHandler(nav_history,      pattern="^earnings:history$"))

    # ── Withdraw ConversationHandler ──────────────────────────────────────────
    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(nav_withdraw, pattern="^nav:withdraw$"),
            CommandHandler("withdraw", nav_withdraw),
        ],
        states={
            PICK_METHOD: [CallbackQueryHandler(pick_method, pattern="^wdraw:method:")],
            ENTER_DEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_destination),
                CommandHandler("cancel", cancel_withdraw),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_withdraw)],
        per_message=False,
    )
    app.add_handler(withdraw_conv)

    # ── Admin ConversationHandler ─────────────────────────────────────────────
    admin_conv = ConversationHandler(
        entry_points=[
            CommandHandler("admin", cmd_admin),
            CallbackQueryHandler(admin_callback, pattern="^adm:"),
        ],
        states={
            ADD_TASK_TITLE:   [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_title)],
            ADD_TASK_CHAT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_chat)],
            ADD_TASK_LINK:    [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_link)],
            BROADCAST_TEXT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
            EDIT_SETTING:     [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_setting_value)],
            WREJECT_REASON:   [MessageHandler(filters.TEXT & ~filters.COMMAND, wreject_reason_text)],
            EDIT_TASK_TITLE:  [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_title)],
            EDIT_TASK_CHAT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_chat)],
            EDIT_TASK_LINK:   [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_task_link)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── Reply keyboard text handler ───────────────────────────────────────────
    # Must be registered AFTER ConversationHandlers so it doesn't
    # intercept messages meant for conversation steps.
    KEYBOARD_FILTER = filters.Regex(
        "^(🏠 Home|📋 Tasks|💰 Earnings|📤 Share|👥 Refer|💸 Withdraw)$"
    )
    app.add_handler(MessageHandler(filters.TEXT & KEYBOARD_FILTER, reply_kb_handler))

    log.info("Bot starting...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()