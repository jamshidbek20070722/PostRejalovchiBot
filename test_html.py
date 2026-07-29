from aiogram.types import Message, MessageEntity, Chat
from aiogram.enums import MessageEntityType
msg = Message(
    message_id=1,
    date=1,
    chat=Chat(id=1, type="private"),
    text="Hello 😜",
    entities=[MessageEntity(type=MessageEntityType.CUSTOM_EMOJI, offset=6, length=2, custom_emoji_id="123456")]
)
with open("output.txt", "w", encoding="utf-8") as f:
    f.write(msg.html_text)
