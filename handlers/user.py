import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

import config
import keyboards.reply as kb
import database.models as db
from states.states import UserStates

logger = logging.getLogger(__name__)
router = Router()

@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    # Clear state first
    await state.clear()
    
    user_id = message.from_user.id
    admin_status = await db.is_admin(user_id)
    logger.info(f"User {user_id} start check: is_admin={admin_status}")
    
    if not admin_status:
        await message.answer(
            "👋 Xush kelibsiz!\n\nBu bot faqatgina kanal administratorlari uchun "
            "postlarni rejalashtirish maqsadida yaratilgan maxsus tizimdir.\n"
            "Agar savollaringiz yoki takliflaringiz bo'lsa, quyidagi tugma orqali adminga murojaat qilishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Adminga xabar yo'llash", callback_data="contact_admin")]
            ])
        )
        return
        
    global_pause = await db.get_global_setting("global_pause", False)
    welcome_text = (
        f"👋 <b>Assalomu alaykum, {message.from_user.full_name}!</b>\n\n"
        "⚙️ Siz adminsiz, quyidagi panel orqali botni boshqarishingiz mumkin:"
    )
    await message.answer(welcome_text, reply_markup=kb.get_admin_menu(global_pause), parse_mode="HTML")


@router.callback_query(F.data == "contact_admin")
async def contact_admin_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.waiting_for_admin_message)
    await callback.message.answer(
        "✍️ Adminga yubormoqchi bo'lgan xabaringizni yozing:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_contact")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_contact")
async def cancel_contact_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Xabar yuborish bekor qilindi.")
    await callback.answer()


@router.message(UserStates.waiting_for_admin_message)
async def forward_to_admin_process(message: Message, state: FSMContext):
    # Forward the message to the OWNER_ID
    try:
        username_val = message.from_user.username or "yo'q"
        text_content = message.html_text or message.text
        await message.bot.send_message(
            chat_id=config.OWNER_ID,
            text=f"✉️ <b>Adminga yangi xabar!</b>\n\n"
                 f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
                 f"🆔 ID: <code>{message.from_user.id}</code>\n"
                 f"🔗 Username: @{username_val}\n\n"
                 f"💬 Xabar:\n{text_content}",
            parse_mode="HTML"
        )
        await message.answer("✅ Xabaringiz adminga muvaffaqiyatli yuborildi!")
    except Exception as e:
        await message.answer(f"❌ Xabar yuborishda xatolik yuz berdi: {e}")
        logger.error(f"Failed to forward message to admin: {e}")
    
    await state.clear()
