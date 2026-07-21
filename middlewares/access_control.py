import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

import config
import database.models as db

logger = logging.getLogger(__name__)

class AccessControlMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user_id = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user_id = event.from_user.id
            
        if user_id:
            # Check if the user is authorized as an Admin (Owner or DB Admin)
            if await db.is_admin(user_id):
                return await handler(event, data)
                
            # If not admin:
            if isinstance(event, Message):
                # Allow CommandStart (/start)
                if event.text and event.text.startswith("/start"):
                    return await handler(event, data)
                    
                # Allow messages if they are currently in the waiting_for_admin_message state
                state = data.get("state")
                if state:
                    current_state = await state.get_state()
                    if current_state == "UserStates:waiting_for_admin_message":
                        return await handler(event, data)
                        
                # Otherwise, block the message and send the restricted access text
                await event.answer(
                    "👋 Xush kelibsiz!\n\nBu bot faqatgina kanal administratorlari uchun "
                    "postlarni rejalashtirish maqsadida yaratilgan maxsus tizimdir.\n"
                    "Agar savollaringiz yoki takliflaringiz bo'lsa, quyidagi tugma orqali adminga murojaat qilishingiz mumkin.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✍️ Adminga xabar yo'llash", callback_data="contact_admin")]
                    ])
                )
                return
                
            elif isinstance(event, CallbackQuery):
                # Allow contact_admin and cancel_contact callback queries, and react queries from channels
                if event.data in ["contact_admin", "cancel_contact"] or (event.data and event.data.startswith("react:")):
                    return await handler(event, data)
                    
                # Otherwise, answer the callback query showing access denied
                await event.answer("Sizda ushbu amalni bajarishga ruxsat yo'q!", show_alert=True)
                return
                
        return await handler(event, data)
