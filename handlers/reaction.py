import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramBadRequest

import database.models as db
from keyboards.inline import get_reaction_keyboard

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data.startswith("react:"))
async def process_reaction_callback(callback_query: CallbackQuery):
    # Format: react:{channel_id}:{message_id}:{reaction_type}
    parts = callback_query.data.split(":")
    if len(parts) < 4:
        await callback_query.answer("❌ Noto'g'ri so'rov!")
        return
        
    try:
        channel_id = int(parts[1])
        message_id = int(parts[2])
        reaction_type = parts[3]
    except ValueError:
        await callback_query.answer("❌ Noto'g'ri format!")
        return
        
    user_id = callback_query.from_user.id
    
    # 1. Update reaction in DB
    result = await db.add_or_update_reaction(
        channel_id=channel_id,
        message_id=message_id,
        user_id=user_id,
        reaction_type=reaction_type
    )
    
    # 2. Get updated counts
    updated_counts = await db.get_reaction_counts(channel_id, message_id)
    
    # 3. Retrieve the original post from DB to get the full reaction options configured
    post = await db.get_posts_col().find_one({
        "target_channel": channel_id,
        "msg_id": message_id
    })
    
    if not post:
        # Fallback if post doc not found: use all reactions currently voted plus this one
        reactions = list(updated_counts.keys())
        if reaction_type not in reactions:
            reactions.append(reaction_type)
    else:
        reactions = post["schedule_config"].get("reactions", [])
        
    # 4. Generate new inline keyboard
    new_markup = get_reaction_keyboard(channel_id, message_id, reactions, updated_counts)
    
    # 5. Answer Callback Query
    answer_text = "Rahmat! Reaksiyangiz qabul qilindi."
    if result == "removed":
        answer_text = "Reaksiyangiz olib tashlandi."
    elif result == "updated":
        answer_text = "Reaksiyangiz yangilandi."
        
    try:
        await callback_query.answer(text=answer_text)
    except Exception as e:
        logger.error(f"Failed to answer callback query: {e}")
        
    # 6. Update message reply markup in the channel
    try:
        await callback_query.bot.edit_message_reply_markup(
            chat_id=channel_id,
            message_id=message_id,
            reply_markup=new_markup
        )
    except TelegramBadRequest as e:
        # If the reply markup is the same (e.g. concurrent clicking or race conditions), Telegram throws an error. We can safely ignore it.
        if "message is not modified" in str(e).lower():
            logger.debug("Message was not modified during reaction update.")
        else:
            logger.error(f"TelegramBadRequest when updating reaction keyboard: {e}")
    except Exception as e:
        logger.error(f"Unexpected error when updating reaction keyboard: {e}")
