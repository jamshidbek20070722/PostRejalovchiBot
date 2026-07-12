from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder

def get_user_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📊 Status"),
        KeyboardButton(text="ℹ️ About")
    )
    builder.row(
        KeyboardButton(text="👥 Support")
    )
    return builder.as_markup(resize_keyboard=True)


def get_admin_menu(global_pause: bool = False) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    pause_text = "▶️ Resume Jobs" if global_pause else "⏸️ Emergency Stop"
    
    builder.row(
        KeyboardButton(text="📊 Bot Stats"),
        KeyboardButton(text="➕ Schedule Post"),
        KeyboardButton(text="👀 Preview Queue")
    )
    builder.row(
        KeyboardButton(text=pause_text),
        KeyboardButton(text="📢 Manage Channels")
    )
    builder.row(
        KeyboardButton(text="🔄 Force Subscription"),
        KeyboardButton(text="👤 Manage Admins")
    )
    builder.row(
        KeyboardButton(text="⬅️ User Menu")
    )
    return builder.as_markup(resize_keyboard=True)


def get_channels_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Add Channel"),
        KeyboardButton(text="➖ Remove Channel")
    )
    builder.row(
        KeyboardButton(text="📝 Update Footer")
    )
    builder.row(
        KeyboardButton(text="🔙 Back to Admin")
    )
    return builder.as_markup(resize_keyboard=True)


def get_admins_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="➕ Add Admin"),
        KeyboardButton(text="➖ Remove Admin")
    )
    builder.row(
        KeyboardButton(text="📋 List Admins")
    )
    builder.row(
        KeyboardButton(text="🔙 Back to Admin")
    )
    return builder.as_markup(resize_keyboard=True)


def get_force_sub_menu() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📋 Force Sub Channels"),
        KeyboardButton(text="🔄 Toggle Channel Force Sub")
    )
    builder.row(
        KeyboardButton(text="🔙 Back to Admin")
    )
    return builder.as_markup(resize_keyboard=True)


def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="❌ Cancel"))
    return builder.as_markup(resize_keyboard=True)


def get_ingestion_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📥 Done Ingesting"))
    builder.row(KeyboardButton(text="❌ Cancel"))
    return builder.as_markup(resize_keyboard=True)


def get_schedule_mode_keyboard() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="⏰ Every Day (Fixed)"),
        KeyboardButton(text="⏳ Every N Days")
    )
    builder.row(
        KeyboardButton(text="🎲 Random Window")
    )
    builder.row(
        KeyboardButton(text="❌ Cancel"))
    return builder.as_markup(resize_keyboard=True)
