import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import BadRequest
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
from handlers.start    import cmd_start, nav_start, REPLY_KEYBOARD
from handlers.tasks    import nav_tasks, task_view, task_verify
from handlers.earnings import nav_earnings, claim_daily, show_leaderboard
from handlers.referral import nav_refer, nav_share
from handlers.withdraw import (
    nav_withdraw, pick_method, enter_destination, cancel_withdraw,
    PICK_METHOD, ENTER_DEST,
)
from handlers.admin import (
    cmd_admin, admin_callback, cancel,
    add_task_title, add_task_chat, add_task_link,
    edit_setting_value, broadcast_text,
    ADD_TASK_TITLE, ADD_TASK_CHAT, ADD_TASK_LINK,
    EDIT_SETTING_VAL, BROADCAST_TEXT,
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s - %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    await db.init_schema()
    log.info("DB schema ready.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    err = context.error
    if isinstance(err, BadRequest) and "Message is not modified" in str(err):
        return
    log.error("Unhandled exception", exc_info=err)


# ── Slash command handlers ────────────────────────────────────────────────────

async def cmd_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_tasks(update, context)

async def cmd_earnings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_earnings(update, context)

async def cmd_refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await nav_refer(update, context)


# ── Reply keyboard router ─────────────────────────────────────────────────────

async def reply_kb_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🏠 Home":
        await nav_start(update, context)
    elif text == "📋 Tasks":
        await nav_tasks(update, context)
    elif text == "💰 Earnings":
        await nav_earnings(update, context)
    elif text == "🎯 Refer & Earn":
        await nav_refer(update, context)
    elif text == "💸 Withdraw":
        return await nav_withdraw(update, context)


def main():
    token = os.environ["BOT_TOKEN"]
    app   = (
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
    app.add_handler(CommandHandler("admin",    cmd_admin))

    # ── Inline nav callbacks ──────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_start,    pattern="^nav:start$"))
    app.add_handler(CallbackQueryHandler(nav_tasks,    pattern="^nav:tasks$"))
    app.add_handler(CallbackQueryHandler(nav_refer,    pattern="^nav:refer$"))
    app.add_handler(CallbackQueryHandler(nav_share,    pattern="^nav:share$"))
    app.add_handler(CallbackQueryHandler(nav_earnings, pattern="^nav:earnings$"))

    # ── Task callbacks ────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(task_view,   pattern="^task:view:[0-9]+$"))
    app.add_handler(CallbackQueryHandler(task_verify, pattern="^task:verify:[0-9]+$"))

    # ── Earnings callbacks ────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(claim_daily,      pattern="^earnings:daily$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern="^earnings:leaderboard$"))

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
            EDIT_SETTING_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_setting_value)],
            BROADCAST_TEXT:   [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── Reply keyboard handler — AFTER ConversationHandlers ───────────────────
    KEYBOARD_FILTER = filters.Regex(
        "^(🏠 Home|📋 Tasks|💰 Earnings|🎯 Refer & Earn|💸 Withdraw)$"
    )
    app.add_handler(MessageHandler(filters.TEXT & KEYBOARD_FILTER, reply_kb_handler))

    log.info("Bot starting...")
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()