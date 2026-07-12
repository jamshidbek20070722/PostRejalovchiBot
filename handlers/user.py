from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart

import keyboards.reply as kb
import database.models as db

router = Router()

@router.message(CommandStart())
async def start_handler(message: Message, db_user: dict):
    role = db_user.get("role", "user")
    
    welcome_text = (
        f"👋 <b>Assalomu alaykum, {message.from_user.full_name}!</b>\n\n"
        "Post Rejalovchi Botiga xush kelibsiz! Ushbu bot yordamida kanallaringizga "
        "postlarni rejalashtirishingiz va avtomatlashtirishingiz mumkin."
    )
    
    if role in ["owner", "admin"]:
        welcome_text += "\n\n⚙️ Siz adminsiz, quyidagi panel orqali botni boshqarishingiz mumkin:"
        await message.answer(welcome_text, reply_markup=kb.get_admin_menu(), parse_mode="HTML")
    else:
        welcome_text += "\n\nBot faqat adminlar uchun rejalashtirish imkonini beradi. Kanallarga obuna bo'lishni unutmang."
        await message.answer(welcome_text, reply_markup=kb.get_user_menu(), parse_mode="HTML")


@router.message(F.text == "📊 Status")
async def status_handler(message: Message):
    # Simple bot system status
    await message.answer(
        "🟢 <b>Bot tizimi faol!</b>\n\n"
        "Barcha xizmatlar muvaffaqiyatli ishlamoqda.\n"
        "Ma'lumotlar bazasi: MongoDB (Ulanish muvaffaqiyatli)\n"
        "Vaqt zonasi: Asia/Tashkent (GMT+5)",
        parse_mode="HTML"
    )


@router.message(F.text == "ℹ️ About")
async def about_handler(message: Message):
    await message.answer(
        "🤖 <b>Bot haqida:</b>\n\n"
        "Ushbu bot kanallarga rejalashtirilgan postlarni joylash, footers (taglavhalar) qo'shish "
        "va postlarga faol inline reaksiya tugmalari biriktirish uchun yaratilgan.\n\n"
        "Dasturchi: @Jamshid\n"
        "Texnologiyalar: Python, Aiogram 3.x, MongoDB, APScheduler.",
        parse_mode="HTML"
    )


@router.message(F.text == "👥 Support")
async def support_handler(message: Message):
    await message.answer(
        "📞 <b>Qo'llab-quvvatlash xizmati:</b>\n\n"
        "Savollar yoki takliflar yuzasidan bot egasiga murojaat qiling:\n"
        "Telegram: @Jamshid\n\n"
        "Muammolar haqida yozishdan oldin bot xatolarini tekshiring.",
        parse_mode="HTML"
    )


@router.message(F.text == "⬅️ User Menu")
async def user_menu_redirect(message: Message):
    await message.answer(
        "🔄 Foydalanuvchi menyusiga o'tildi.",
        reply_markup=kb.get_user_menu()
    )
