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
    text = 'Test premium emoji: 😁'
    # 'Test premium emoji: 😁' length is 20 + 2 (surrogate pair for emoji) = 22 in UTF-16
    # offset for emoji is 20, length is 2 in UTF-16
    ent = MessageEntity(type=MessageEntityType.CUSTOM_EMOJI, offset=20, length=2, custom_emoji_id="5368324170671202286")
    try:
        msg = await bot.send_message(chat_id=DB_CHANNEL_ID, text=text, entities=[ent])
        print("Entities in sent message:", getattr(msg, 'entities', None))
    except Exception as e:
        print("Failed:", e)
    await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
