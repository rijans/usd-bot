import asyncio
from core.db import init_schema
asyncio.run(init_schema())
print("Database seeded with fake users.")
