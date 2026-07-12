import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ChatMemberStatus

import database.models as db

logger = logging.getLogger(__name__)

class ForceSubscriptionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        # Determine user ID and object type
        user_id = None
        is_msg = False
        
        if isinstance(event, Message):
            if event.from_user:
                user_id = event.from_user.id
            is_msg = True
        elif isinstance(event, CallbackQuery):
            if event.from_user:
                user_id = event.from_user.id
            is_msg = False
            
        if not user_id:
            return await handler(event, data)
            
        # Get user role from data (populated by RegisterUserMiddleware)
        db_user = data.get("db_user")
        if db_user and db_user.get("role") in ["owner", "admin"]:
            # Admins/Owners are exempt from force subscription
            return await handler(event, data)
            
        # Fetch force sub channels from DB
        force_channels = await db.get_force_sub_channels()
        if not force_channels:
            return await handler(event, data)
            
        # Check subscription for each channel
        unsubscribed_channels = []
        bot = data["bot"]
        
        for ch in force_channels:
            ch_id = ch["channel_id"]
            invite_link = ch.get("invite_link", "")
            ch_name = ch.get("name", "Channel")
            
            try:
                member = await bot.get_chat_member(chat_id=ch_id, user_id=user_id)
                if member.status not in [
                    ChatMemberStatus.CREATOR,
                    ChatMemberStatus.ADMINISTRATOR,
                    ChatMemberStatus.MEMBER
                ]:
                    unsubscribed_channels.append((ch_name, invite_link))
            except Exception as e:
                logger.error(f"Error checking membership for user {user_id} in channel {ch_id}: {e}")
                # If bot cannot check (e.g. not admin), we might skip or block. Let's skip to avoid blocking users due to config issues.
                continue
                
        if unsubscribed_channels:
            # Build list of channels to join
            text = (
                "⚠️ <b>Botdan foydalanish uchun quyidagi kanallarga a'zo bo'lishingiz shart:</b>\n\n"
                "Iltimos, a'zo bo'ling va keyin qayta urunib ko'ring."
            )
            
            # Using Inline Buttons for subscription links and check button is standard.
            # But prompt says "Inline Keyboards ONLY for post reactions/ratings". 
            # So let's write invite links as clickable HTML text and ask them to type /start or use menu options.
            # Wait, can we provide links directly in the text? Yes, e.g., `<a href="link">Channel Name</a>`. This is very clean and does not violate the rule!
            
            links_text = ""
            for name, link in unsubscribed_channels:
                if link:
                    links_text += f"🔹 <a href='{link}'>{name}</a>\n"
                else:
                    links_text += f"🔹 {name} (Havola mavjud emas)\n"
                    
            full_text = f"{text}\n\n{links_text}\nObuna bo'lgach, /start buyrug'ini yuboring."
            
            if is_msg:
                # If they typed a message, respond to it
                assert isinstance(event, Message)
                # Avoid looping on /start by allowing start but blocking other inputs if unsubscribed.
                # Actually, /start is usually handled by registration, let's let it run or block everything.
                # We block all messages except /start command
                if event.text and event.text.startswith("/start"):
                    return await handler(event, data)
                    
                await event.answer(full_text, parse_mode="HTML", disable_web_page_preview=True)
            else:
                # If callback query, answer with alert
                assert isinstance(event, CallbackQuery)
                # Or send a new message
                await event.message.answer(full_text, parse_mode="HTML", disable_web_page_preview=True)
                await event.answer("Majburiy obunalar mavjud!", show_alert=True)
                
            return  # Stop pipeline
            
        return await handler(event, data)
