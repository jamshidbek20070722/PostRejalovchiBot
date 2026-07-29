import asyncio
from aiogram import Bot
from aiogram.types import MessageEntity
from aiogram.enums import MessageEntityType
import os
from dotenv import load_dotenv

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_CHANNEL_ID = os.getenv("DB_CHANNEL_ID")

async def main():
    bot = Bot(token=BOT_TOKEN)
    text = 'Test premium emoji: 👍'
    ent = MessageEntity(type=MessageEntityType.CUSTOM_EMOJI, offset=20, length=1, custom_emoji_id="5368324170671202286")
    try:
        msg = await bot.send_message(chat_id=DB_CHANNEL_ID, text=text, entities=[ent])
        print("Entities:", msg.entities)
    except Exception as e:
        print("Failed:", e)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
