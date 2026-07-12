import logging
from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery

import config
import database.models as db

logger = logging.getLogger(__name__)

class RegisterUserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        user = None
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            user = event.from_user
            
        if user:
            # Check if user already exists
            user_db = await db.get_user(user.id)
            if not user_db:
                # Is this the owner?
                role = "owner" if user.id == config.OWNER_ID else "user"
                user_db = await db.register_user(user.id, role=role)
                logger.info(f"Registered new user {user.id} with role {role}")
            else:
                # Ensure owner role is set correctly if owner ID matches
                if user.id == config.OWNER_ID and user_db.get("role") != "owner":
                    await db.update_user_role(user.id, "owner")
                    user_db["role"] = "owner"
                    
            # Inject user doc into handler data context for easy access
            data["db_user"] = user_db
            
        return await handler(event, data)
