import asyncio
from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CHANNEL_ID = os.getenv("DB_CHANNEL_ID")

async def main():
    bot = Bot(token=BOT_TOKEN)
    text = 'Test premium emoji: <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>'
    try:
        await bot.send_message(chat_id=DB_CHANNEL_ID, text=text, parse_mode="HTML")
        print("Sent successfully")
    except Exception as e:
        print("Failed:", e)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
