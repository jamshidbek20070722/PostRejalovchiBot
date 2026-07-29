import asyncio
from aiogram import Bot
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CHANNEL_ID = os.getenv("DB_CHANNEL_ID")

async def main():
    bot = Bot(token=BOT_TOKEN)
    # Forward the last message to the bot itself or just get history? Bots can't get history.
    # I can send a message and look at the returned Message object!
    text = 'Test premium emoji: <tg-emoji emoji-id="5368324170671202286">👍</tg-emoji>'
    try:
        msg = await bot.send_message(chat_id=DB_CHANNEL_ID, text=text, parse_mode="HTML")
        print("Entities:", msg.entities)
    except Exception as e:
        print("Failed:", e)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
