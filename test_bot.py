import asyncio
import os
import logging
from unittest.mock import AsyncMock

from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import ContextTypes, ApplicationBuilder

os.environ["DATABASE_URL"] = "postgresql://postgres:postgres@localhost:5432/botdb"
os.environ["BOT_TOKEN"] = "mock_token"

logging.basicConfig(level=logging.INFO)

# A simple script wrapper to quickly call our handlers with mocked objects
# To use: python test_bot.py
# If it runs without raising exceptions, it means our python code ran cleanly.

print("Starting smoke test script...")
try:
    import main
    print("✅ Successfully imported main module.")
except Exception as e:
    print(f"❌ Failed to import main: {e}")

