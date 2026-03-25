import logging
import os
import asyncio
import datetime
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest, Conflict
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

import core.db as db
from handlers.start    import cmd_start, nav_start
from handlers.tasks    import nav_tasks, task_view, task_verify
from handlers.earnings import nav_earnings, claim_daily, show_leaderboard, nav_history
from handlers.referral import nav_share, nav_refer
from handlers.faq import nav_faq, faq_section, ticket_new_start, ticket_receive, ticket_cancel, ticket_status, TICKET_WRITE
from handlers.profile import (
    nav_profile, profile_edit_start, profile_receive_value,
    profile_receive_phone_share, profile_receive_location_share, cancel_profile,
    EDIT_PROFILE_VALUE, AWAIT_PHONE_SHARE, AWAIT_LOCATION_SHARE,
)
from handlers.withdraw import (
    nav_withdraw, pick_method, use_saved_address, enter_destination, cancel_withdraw,
    PICK_METHOD, ENTER_DEST, USE_SAVED,
)
from handlers.luckydraw import (
    show_lucky_draw_menu, handle_buy_ticket_click, show_past_winners,
    precheckout_callback, successful_payment_callback
)
from handlers.admin import (
    cmd_admin, admin_callback, cancel, edit_setting_value,
    add_task_title, add_task_chat, add_task_link,
    edit_task_title, edit_task_chat, edit_task_link,
    broadcast_text, wreject_reason_text, lookup_user_text,
    ADD_TASK_TITLE, ADD_TASK_CHAT, ADD_TASK_LINK,
    BROADCAST_TEXT, EDIT_SETTING, WREJECT_REASON,
    EDIT_TASK_TITLE, EDIT_TASK_CHAT, EDIT_TASK_LINK,
    LOOKUP_USER, admin_ids,
    cmd_addbalance, cmd_deductbalance, cmd_setbalance,
    admin_ticket_reply_text, ADMIN_REPLY_TICKET
)
from handlers.groups import nav_groups, group_callback

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=getattr(logging, os.environ.get("LOG_LEVEL", "WARNING")),
)
log = logging.getLogger(__name__)


async def daily_bonus_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetch("SELECT user_id, full_name FROM users WHERE user_id > 0 AND (last_daily IS NULL OR last_daily < CURRENT_DATE)")
        for u in users:
            name = u["full_name"] or "User"
            msg = f"🎁 *Your daily bonus is ready, {name}!*\n\nClaim it now from the 💰 Earnings menu! (Requires 2 invites this week to activate)"
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Claim Daily Bonus", callback_data="earnings:daily")]])
            try:
                await context.bot.send_message(u["user_id"], msg, parse_mode="Markdown", reply_markup=keyboard)
                await asyncio.sleep(0.05) # Safe rate limit: 20 msgs per sec
            except Exception:
                pass

async def test_daily_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in admin_ids():
        return
    await update.message.reply_text("Triggering test daily broadcast...")
    await daily_bonus_reminder(context)
    await update.message.reply_text("Broadcast complete.")


async def cleanup_deleted_accounts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check all users — if Telegram says 'deactivated', delete them from DB."""
    user_ids = await db.get_all_real_user_ids()
    deleted_count = 0
    for uid in user_ids:
        try:
            await context.bot.send_chat_action(chat_id=uid, action="typing")
        except Exception as e:
            err_str = str(e).lower()
            if "deactivated" in err_str or "not found" in err_str:
                await db.delete_user(uid)
                deleted_count += 1
                log.info(f"Cleaned up deleted account: {uid}")
        await asyncio.sleep(0.05)  # Rate limit
    log.info(f"Account cleanup done. Removed {deleted_count} deleted accounts.")


async def test_cleanup_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in admin_ids():
        return
    await update.message.reply_text("Scanning for deleted accounts...")
    await cleanup_deleted_accounts(context)
    await update.message.reply_text("Cleanup complete.")

async def finish_lucky_draw_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cron job: Picks 3 fake users to win the draw and notifies all real participants."""
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        # 1. Randomly pick 3 fake users
        # Fake users have user_id < 0. We order by random()
        fake_pool = await conn.fetch("SELECT user_id FROM users WHERE user_id < 0 ORDER BY random() LIMIT 3")
        if len(fake_pool) < 3:
            log.warning("Not enough fake users to select Lucky Draw winners! Need 3.")
            return

        w1_id, w2_id, w3_id = fake_pool[0]["user_id"], fake_pool[1]["user_id"], fake_pool[2]["user_id"]
        
        # Fetch current prize settings
        p1 = await db.get_setting("ld_prize_1", "200")
        p2 = await db.get_setting("ld_prize_2", "70")
        p3 = await db.get_setting("ld_prize_3", "30")

        # 2. Record the winners
        await db.set_today_lucky_draw_winners(w1_id, w2_id, w3_id, p1, p2, p3)

        # 3. Inform all REAL users who participated today
        participants = await db.get_today_lucky_draw_participants()
        
        msg = (
            "🎰 <b>Today's Lucky Draw has Concluded!</b> 🎰\n\n"
            "The daily draw is officially over, and the top 3 winners have been finalized.\n"
            "Thank you for participating today!\n\n"
            "👇 Tap the button below to see the official winning list:"
        )
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 View Prize Winners", callback_data="ld:winners")]])
        
        count = 0
        for uid in participants:
            try:
                await context.bot.send_message(uid, msg, reply_markup=keyboard, parse_mode="HTML")
                count += 1
                await asyncio.sleep(0.05)
            except Exception:
                pass
                
        log.info(f"Lucky Draw resolved. Notified {count} real participants.")

async def test_draw_job(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in admin_ids():
        return
    await update.message.reply_text("Triggering Lucky Draw midnight resolution cron job...")
    await finish_lucky_draw_job(context)
    await update.message.reply_text("Draw resolved and broadcasts sent.")

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

    # Migration: add prize columns if they don't exist
    pool = await db.get_pool()
    async with pool.acquire() as conn:
        try:
            await conn.execute("ALTER TABLE lucky_draw_winners ADD COLUMN IF NOT EXISTS prize_1 TEXT NOT NULL DEFAULT '200'")
            await conn.execute("ALTER TABLE lucky_draw_winners ADD COLUMN IF NOT EXISTS prize_2 TEXT NOT NULL DEFAULT '70'")
            await conn.execute("ALTER TABLE lucky_draw_winners ADD COLUMN IF NOT EXISTS prize_3 TEXT NOT NULL DEFAULT '30'")
            log.info("Lucky Draw Winners prize columns migration done.")
        except Exception as e:
            log.error(f"Migration error: {e}")
    
    # Schedule daily bonus reminder at 10:00 UTC
    t = datetime.time(hour=10, minute=0, tzinfo=datetime.timezone.utc)
    application.job_queue.run_daily(daily_bonus_reminder, t)
    log.info(f"Daily job scheduled at {t} UTC")

    # Schedule group auto-promotion check every 5 minutes
    application.job_queue.run_repeating(auto_promote_job, interval=300, first=60)
    log.info("Group auto-promoter job scheduled (every 5 min)")

    # Schedule deleted account cleanup every Sunday at 03:00 UTC
    application.job_queue.run_daily(
        cleanup_deleted_accounts,
        datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc),
        days=(6,),  # 6=Sunday
    )
    log.info("Weekly account cleanup scheduled (Sundays 03:00 UTC)")

    # Schedule Lucky Draw winner selection every day at 23:58 UTC
    ld_t = datetime.time(hour=23, minute=58, tzinfo=datetime.timezone.utc)
    application.job_queue.run_daily(finish_lucky_draw_job, ld_t)
    log.info(f"Daily Lucky Draw resolution scheduled at {ld_t} UTC")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    err_str = str(err)

    # Filter out noisy, harmless errors
    if isinstance(err, BadRequest):
        if "Message is not modified" in err_str: return
        if "Query is too old" in err_str: return
        if "id is invalid" in err_str: return
        
    if "ReadError" in err_str or "timeout expired" in err_str:
        log.warning(f"Network issue (Read/Timeout): {err_str}")
        return

    if isinstance(err, Conflict):
        log.warning("Conflict error detected - this is normal during bot restart/deployment.")
        return
    
    log.error("Unhandled exception", exc_info=err)
    
    # Notify admins
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
    elif text in ("🤝 Refer & Earn", "📤 Share", "👥 Refer"):
        await nav_refer(update, context)
    elif text in ("❓ FAQ", "❓ FAQ & Support"):
        await nav_faq(update, context)
    elif text == "💸 Withdraw":
        await nav_withdraw(update, context)
    elif text == "👤 Profile":
        await nav_profile(update, context)
    elif text == "🎰 Lucky Draw":
        await show_lucky_draw_menu(update, context)

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
        .read_timeout(30)
        .connect_timeout(30)
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
    app.add_handler(CommandHandler("test_cleanup", test_cleanup_job))
    app.add_handler(CommandHandler("test_draw_job", test_draw_job))
    app.add_handler(CommandHandler("profile", nav_profile))
    app.add_handler(CommandHandler("mygroups", nav_groups))
    
    # Balance fixes
    app.add_handler(CommandHandler("addbalance", cmd_addbalance))
    app.add_handler(CommandHandler("deductbalance", cmd_deductbalance))
    app.add_handler(CommandHandler("setbalance", cmd_setbalance))


    # ── Inline nav buttons ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_start,    pattern="^nav:start$"))
    app.add_handler(CallbackQueryHandler(nav_tasks,    pattern="^nav:tasks$"))
    app.add_handler(CallbackQueryHandler(nav_share,    pattern="^nav:share$"))
    app.add_handler(CallbackQueryHandler(nav_earnings, pattern="^nav:earnings$"))
    app.add_handler(CallbackQueryHandler(nav_refer,    pattern="^nav:refer$"))
    app.add_handler(CallbackQueryHandler(nav_faq,      pattern="^nav:faq$"))
    app.add_handler(CallbackQueryHandler(faq_section,  pattern="^faq:"))
    app.add_handler(CallbackQueryHandler(nav_profile,  pattern="^nav:profile$"))
    app.add_handler(CallbackQueryHandler(ticket_status, pattern="^ticket:status$"))

    # ── Ticket Submission ConversationHandler ─────────────────────────────
    ticket_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(ticket_new_start, pattern="^ticket:new$")],
        states={
            TICKET_WRITE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, ticket_receive),
                CommandHandler("cancel", ticket_cancel),
            ],
        },
        fallbacks=[CommandHandler("cancel", ticket_cancel)],
        per_message=False,
    )
    app.add_handler(ticket_conv)

    # ── Lucky Draw Callbacks & Payments ──────────────────────────────────────
    app.add_handler(CallbackQueryHandler(show_lucky_draw_menu, pattern="^nav:luckydraw$"))
    app.add_handler(CallbackQueryHandler(handle_buy_ticket_click, pattern="^ld:buy:"))
    app.add_handler(CallbackQueryHandler(show_past_winners, pattern="^ld:winners$"))
    app.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))

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
            USE_SAVED:   [CallbackQueryHandler(use_saved_address, pattern="^wdraw:(use_saved|enter_new)$")],
            ENTER_DEST: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_destination),
                CommandHandler("cancel", cancel_withdraw),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_withdraw)],
        per_message=False,
    )
    app.add_handler(withdraw_conv)

    # ── Profile ConversationHandler ─────────────────────────────────────────────
    profile_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(profile_edit_start, pattern="^prof:edit:"),
        ],
        states={
            EDIT_PROFILE_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_receive_value),
                CommandHandler("cancel", cancel_profile),
            ],
            AWAIT_PHONE_SHARE: [
                MessageHandler(filters.CONTACT, profile_receive_phone_share),
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_receive_value),
                CommandHandler("cancel", cancel_profile),
            ],
            AWAIT_LOCATION_SHARE: [
                MessageHandler(filters.LOCATION, profile_receive_location_share),
                MessageHandler(filters.TEXT & ~filters.COMMAND, profile_receive_value),
                CommandHandler("cancel", cancel_profile),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_profile)],
        per_message=False,
    )
    app.add_handler(profile_conv)

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
            LOOKUP_USER:      [
                MessageHandler(filters.TEXT & ~filters.COMMAND, lookup_user_text),
                CallbackQueryHandler(admin_callback, pattern="^adm:")
            ],
            ADMIN_REPLY_TICKET:[MessageHandler(filters.TEXT & ~filters.COMMAND, admin_ticket_reply_text)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("admin", cmd_admin)
        ],
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── Reply keyboard text handler ───────────────────────────────────────────
    # Must be registered AFTER ConversationHandlers so it doesn't
    # intercept messages meant for conversation steps.
    KEYBOARD_FILTER = filters.Regex(
        r"^(🏠 Home|📋 Tasks|💰 Earnings|🤝 Refer & Earn|❓ FAQ & Support|❓ FAQ|💸 Withdraw|👤 Profile|🎰 Lucky Draw)$"
    )
    app.add_handler(MessageHandler(filters.TEXT & KEYBOARD_FILTER, reply_kb_handler))

    log.info("Bot starting...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()