import asyncio
from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CHANNEL_ID = os.getenv("DB_CHANNEL_ID")

async def main():
    bot = Bot(token=BOT_TOKEN)
    # The message ID of the premium emoji message sent to the bot: 
    # I don't have one right now, but let's assume I can send one from myself to the bot.
    # Since I can't send one, I'll just print out a plan.
    pass

if __name__ == "__main__":
    asyncio.run(main())
