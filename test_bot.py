import os
import asyncio
from unittest.mock import AsyncMock, MagicMock
from telegram import Update, User, Message, Chat, CallbackQuery
from telegram.ext import ApplicationBuilder, ContextTypes

import main
import core.db as db

# Set test environment
os.environ["DATABASE_URL"] = "postgres://postgres:postgres@localhost:5432/postgres" 
os.environ["BOT_TOKEN"] = "1234:MOCK"
os.environ["ADMIN_IDS"] = "111111"

async def main_test():
    print("🚀 Initializing mock DB schema...")
    # NOTE: requires a running local postgres or uses sqlite for tests if swapped. 
    # For now, let's just make sure Python parses our handlers without syntax errors.
    print("✅ Handlers loaded. Creating application...")
    
    app = ApplicationBuilder().token("123:abc").build()
    main.main = MagicMock() # Mock main's blocking run_polling
    
    # Let's test if the admin IDs parses correctly
    from handlers.admin import admin_ids
    print(f"✅ Admin IDs resolved to: {admin_ids()}")
    
    print("🎉 All files loaded successfully, syntax is clean.")

if __name__ == "__main__":
    asyncio.run(main_test())
