"""
main.py  ─  Entry point. Initializes DB schema, registers all handlers, starts polling.

Railway: runs this via Procfile → worker: python main.py

Key fix: python-telegram-bot v21 manages its own event loop via run_polling().
         Do NOT wrap in asyncio.run(). Use post_init hook for async startup tasks.
"""
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import core.db as db
from handlers.start    import cmd_start, nav_start
from handlers.tasks    import nav_tasks, task_view, task_verify
from handlers.earnings import nav_earnings, claim_daily, show_leaderboard
from handlers.referral import nav_share, nav_refer
from handlers.withdraw import (
    nav_withdraw, pick_method, enter_destination, cancel_withdraw,
    PICK_METHOD, ENTER_DEST,
)
from handlers.admin import (
    cmd_admin, admin_callback, cancel,
    add_task_title, add_task_chat, add_task_link,
    broadcast_text,
    ADD_TASK_TITLE, ADD_TASK_CHAT, ADD_TASK_LINK, BROADCAST_TEXT,
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """
    Called by PTB inside its own event loop after the app initializes.
    Safe place to run async startup tasks like DB schema creation.
    """
    await db.init_schema()
    log.info("✅ Database schema ready.")


def main():
    token = os.environ["BOT_TOKEN"]

    app = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    # ── /start ────────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))

    # ── Nav buttons (the 6-button bottom menu) ────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_start,    pattern=r"^nav:start$"))
    app.add_handler(CallbackQueryHandler(nav_tasks,    pattern=r"^nav:tasks$"))
    app.add_handler(CallbackQueryHandler(nav_share,    pattern=r"^nav:share$"))
    app.add_handler(CallbackQueryHandler(nav_earnings, pattern=r"^nav:earnings$"))
    app.add_handler(CallbackQueryHandler(nav_refer,    pattern=r"^nav:refer$"))

    # ── Tasks ─────────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(task_view,   pattern=r"^task:view:\d+$"))
    app.add_handler(CallbackQueryHandler(task_verify, pattern=r"^task:verify:\d+$"))

    # ── Earnings ──────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(claim_daily,      pattern=r"^earnings:daily$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard, pattern=r"^earnings:leaderboard$"))

    # ── Withdraw ConversationHandler ──────────────────────────────────────────
    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(nav_withdraw, pattern=r"^nav:withdraw$"),
            CommandHandler("withdraw", nav_withdraw),
        ],
        states={
            PICK_METHOD: [CallbackQueryHandler(pick_method, pattern=r"^wdraw:method:")],
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
            CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
        ],
        states={
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_title)],
            ADD_TASK_CHAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_chat)],
            ADD_TASK_LINK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_link)],
            BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(admin_conv)

    log.info("🤖 Bot starting…")
    # run_polling() manages its own event loop — do NOT call inside asyncio.run()
    app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()"""
main.py  ─  Entry point. Initializes DB schema, registers all handlers, starts polling.

Railway: runs this via Procfile → worker: python main.py
"""
import asyncio
import logging
import os

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import core.db as db
from handlers.start    import cmd_start, nav_start
from handlers.tasks    import nav_tasks, task_view, task_verify
from handlers.earnings import nav_earnings, claim_daily, show_leaderboard
from handlers.referral import nav_share, nav_refer
from handlers.withdraw import (
    nav_withdraw, pick_method, enter_destination, cancel_withdraw,
    PICK_METHOD, ENTER_DEST,
)
from handlers.admin import (
    cmd_admin, admin_callback, cancel,
    add_task_title, add_task_chat, add_task_link,
    broadcast_text,
    ADD_TASK_TITLE, ADD_TASK_CHAT, ADD_TASK_LINK, BROADCAST_TEXT,
)

logging.basicConfig(
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


def build_application() -> Application:
    token = os.environ["BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # ── /start ──────────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start", cmd_start))

    # ── Nav buttons (the bottom menu row) ───────────────────────────────────
    app.add_handler(CallbackQueryHandler(nav_start,    pattern=r"^nav:start$"))
    app.add_handler(CallbackQueryHandler(nav_tasks,    pattern=r"^nav:tasks$"))
    app.add_handler(CallbackQueryHandler(nav_share,    pattern=r"^nav:share$"))
    app.add_handler(CallbackQueryHandler(nav_earnings, pattern=r"^nav:earnings$"))
    app.add_handler(CallbackQueryHandler(nav_refer,    pattern=r"^nav:refer$"))

    # ── Tasks ────────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(task_view,   pattern=r"^task:view:\d+$"))
    app.add_handler(CallbackQueryHandler(task_verify, pattern=r"^task:verify:\d+$"))

    # ── Earnings ─────────────────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(claim_daily,       pattern=r"^earnings:daily$"))
    app.add_handler(CallbackQueryHandler(show_leaderboard,  pattern=r"^earnings:leaderboard$"))

    # ── Withdraw ConversationHandler ─────────────────────────────────────────
    withdraw_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(nav_withdraw, pattern=r"^nav:withdraw$"),
            CommandHandler("withdraw", nav_withdraw),
        ],
        states={
            PICK_METHOD: [CallbackQueryHandler(pick_method, pattern=r"^wdraw:method:")],
            ENTER_DEST:  [
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
            CallbackQueryHandler(admin_callback, pattern=r"^adm:"),
        ],
        states={
            ADD_TASK_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_title)],
            ADD_TASK_CHAT:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_chat)],
            ADD_TASK_LINK:  [MessageHandler(filters.TEXT & ~filters.COMMAND, add_task_link)],
            BROADCAST_TEXT: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    )
    app.add_handler(admin_conv)

    # ── /admin shortcut (outside conversation for initial entry) ─────────────
    app.add_handler(CommandHandler("admin", cmd_admin))

    return app


async def main():
    # Init DB schema (idempotent — safe to call on every startup)
    await db.init_schema()
    log.info("✅ Database schema ready.")

    app = build_application()
    log.info("🤖 Bot starting…")
    await app.run_polling(drop_pending_updates=True, allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    asyncio.run(main())
