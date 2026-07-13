from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_admin_menu(global_pause: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    pause_text = "▶️ Ishlarni davom ettirish" if global_pause else "⏸️ Favqulodda to'xtatish"
    
    builder.row(
        KeyboardButton(text="📊 Bot statistikasi"),
        KeyboardButton(text="➕ Post rejalashtirish"),
        KeyboardButton(text="👀 Navbatni ko'rish")
    )
    builder.row(
        KeyboardButton(text=pause_text),
        KeyboardButton(text="📢 Kanallarni boshqarish")
    )
    builder.row(
        KeyboardButton(text="🔄 Majburiy obuna"),
        KeyboardButton(text="👤 Adminlarni boshqarish")
    )
    return builder.as_markup(resize_keyboard=True)


def get_channels_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Kanal qo'shish"),
        KeyboardButton(text="➖ Kanalni o'chirish")
    )
    builder.row(
        KeyboardButton(text="📝 Taglavhani yangilash")
    )
    builder.row(
        KeyboardButton(text="🔙 Admin panelga qaytish")
    )
    return builder.as_markup(resize_keyboard=True)


def get_admins_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Admin qo'shish"),
        KeyboardButton(text="➖ Adminni o'chirish")
    )
    builder.row(
        KeyboardButton(text="📋 Adminlar ro'yxati")
    )
    builder.row(
        KeyboardButton(text="🔙 Admin panelga qaytish")
    )
    return builder.as_markup(resize_keyboard=True)


def get_force_sub_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Majburiy obuna kanallari"),
        KeyboardButton(text="🔄 Kanal obunasini o'zgartirish")
    )
    builder.row(
        KeyboardButton(text="🔙 Admin panelga qaytish")
    )
    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True)


def get_ingestion_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="✅ Yuklashni yakunlash"))
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    return builder.as_markup(resize_keyboard=True)


def get_schedule_mode_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="⏰ Har kuni (Belgilangan vaqtda)"),
        KeyboardButton(text="⏳ Har N kunda")
    )
    builder.row(
        KeyboardButton(text="🎲 Tasodifiy vaqt oralig'ida")
    )
    builder.row(
        KeyboardButton(text="❌ Bekor qilish")
    )
    return builder.as_markup(resize_keyboard=True)
