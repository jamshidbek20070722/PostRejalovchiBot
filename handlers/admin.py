import logging
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext

import config
import keyboards.reply as kb
import database.models as db
from states.states import AdminStates
from services.scheduler import scheduler

logger = logging.getLogger(__name__)
router = Router()

# Custom Filter to check if user is admin/owner
class IsAdminFilter(Filter):
    async def __call__(self, message: Message, db_user: dict) -> bool:
        return db_user.get("role") in ["admin", "owner"]

# Apply Admin Filter to all routes in this router
router.message.filter(IsAdminFilter())


# --- GENERAL NAVIGATION & CANCEL ---

@router.message(F.text == "❌ Cancel")
async def cancel_state_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("❌ Harakat bekor qilindi.", reply_markup=kb.get_admin_menu())


@router.message(F.text == "🔙 Back to Admin")
async def back_to_admin_handler(message: Message, state: FSMContext):
    await state.clear()
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer("🔙 Admin panelga qaytildi.", reply_markup=kb.get_admin_menu(global_pause))


# --- BOT STATS ---

@router.message(F.text == "📊 Bot Stats")
async def bot_stats_handler(message: Message):
    user_stats = await db.get_user_stats()
    post_stats = await db.get_post_stats()
    channels = await db.get_all_channels()
    
    channels_text = ""
    for ch in channels:
        sub_indicator = "🔒" if ch.get("is_force_sub") else "📢"
        channels_text += f"• {sub_indicator} {ch.get('name')} (<code>{ch.get('channel_id')}</code>)\n"
        
    if not channels_text:
        channels_text = "Kanallar qo'shilmagan.\n"
        
    stats_msg = (
        "📊 <b>Bot Statistikasi:</b>\n\n"
        f"👥 <b>Foydalanuvchilar:</b>\n"
        f"  • Umumiy: {user_stats['total_users']}\n"
        f"  • Adminlar: {user_stats['admins']}\n"
        f"  • Ega (Owner): {user_stats['owners']}\n\n"
        f"📢 <b>Ulangan Kanallar:</b>\n"
        f"{channels_text}\n"
        f"📝 <b>Postlar holati:</b>\n"
        f"  • Umumiy: {post_stats['total']}\n"
        f"  • Kutilayotgan: {post_stats['pending']}\n"
        f"  • Yuborilgan: {post_stats['posted']}\n"
        f"  • O'chirib qo'yilgan (Paused): {post_stats['paused']}\n"
        f"  • Xatolik: {post_stats['failed']}\n"
    )
    await message.answer(stats_msg, parse_mode="HTML")


# --- EMERGENCY STOP (GLOBAL PAUSE) ---

@router.message(F.text.in_(["⏸️ Emergency Stop", "▶️ Resume Jobs"]))
async def emergency_stop_handler(message: Message):
    current_pause = await db.get_global_setting("global_pause", False)
    new_pause = not current_pause
    
    await db.set_global_setting("global_pause", new_pause)
    
    if new_pause:
        scheduler.pause()
        await db.get_posts_col().update_many({"status": "pending"}, {"$set": {"status": "paused"}})
        await message.answer(
            "⚠️ <b>Favqulodda To'xtash faollashtirildi!</b>\n\n"
            "Barcha rejalashtirilgan ishlar to'xtatildi. Kanallarga postlar yuborilmaydi.",
            reply_markup=kb.get_admin_menu(new_pause),
            parse_mode="HTML"
        )
    else:
        scheduler.resume()
        await db.get_posts_col().update_many({"status": "paused"}, {"$set": {"status": "pending"}})
        await message.answer(
            "✅ <b>Bot faoliyati tiklandi!</b>\n\n"
            "Tizim ishga tushirildi. Rejalashtirilgan postlar o'z vaqtida yuboriladi.",
            reply_markup=kb.get_admin_menu(new_pause),
            parse_mode="HTML"
        )


# --- MANAGE CHANNELS NAVIGATION ---

@router.message(F.text == "📢 Manage Channels")
async def manage_channels_menu_handler(message: Message):
    await message.answer("📢 Kanallarni boshqarish bo'limi:", reply_markup=kb.get_channels_menu())


# --- ADD CHANNEL ---

@router.message(F.text == "➕ Add Channel")
async def add_channel_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.adding_channel)
    await message.answer(
        "Qo'shmoqchi bo'lgan kanalingiz ma'lumotlarini quyidagi formatda yuboring:\n\n"
        "<code>Kanal_ID Kanal_Nomi Kanal_Ulanish_Havolasi</code>\n\n"
        "Masalan:\n"
        "<code>-10022334455 Yangiliklar https://t.me/yangiliklar</code>\n\n"
        "⚠️ Bot ushbu kanalda administrator bo'lishi shart!",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.adding_channel)
async def add_channel_process(message: Message, state: FSMContext):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 2:
        await message.answer("❌ Xato format. Iltimos ko'rsatilganidek yuboring:\n<code>ID Nomi [Havola]</code>", parse_mode="HTML")
        return
        
    try:
        channel_id = int(parts[0])
    except ValueError:
        await message.answer("❌ Kanal ID si raqamlardan iborat bo'lishi kerak (masalan: -10020304050).")
        return
        
    name = parts[1]
    invite_link = parts[2] if len(parts) > 2 else ""
    
    # Try to verify bot membership/admin rights in channel
    try:
        chat = await message.bot.get_chat(channel_id)
        name = chat.title or name
    except Exception as e:
        await message.answer(
            f"⚠️ Bot kanaldan ma'lumot ololmadi. Bot ushbu kanalda admin ekanligiga ishonch hosil qiling!\n"
            f"Xatolik: {e}"
        )
        return
        
    await db.add_channel(channel_id, name, invite_link)
    await state.clear()
    await message.answer(f"✅ Kanal muvaffaqiyatli qo'shildi:\n<b>{name}</b> ({channel_id})", reply_markup=kb.get_channels_menu(), parse_mode="HTML")


# --- REMOVE CHANNEL ---

@router.message(F.text == "➖ Remove Channel")
async def remove_channel_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.removing_channel)
    channels = await db.get_all_channels()
    
    ch_list = ""
    for ch in channels:
        ch_list += f"• <code>{ch['channel_id']}</code> - {ch['name']}\n"
        
    await message.answer(
        f"Kanal ID sini yuboring:\n\n{ch_list}",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.removing_channel)
async def remove_channel_process(message: Message, state: FSMContext):
    try:
        channel_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID noto'g'ri. Raqamlardan iborat bo'lishi lozim.")
        return
        
    res = await db.remove_channel(channel_id)
    if res:
        await state.clear()
        await message.answer(f"✅ Kanal {channel_id} muvaffaqiyatli o'chirildi.", reply_markup=kb.get_channels_menu())
    else:
        await message.answer("❌ Bunday ID ga ega kanal topilmadi. Qayta urinib ko'ring.")


# --- UPDATE FOOTER ---

@router.message(F.text == "📝 Update Footer")
async def update_footer_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.updating_footer_channel_select)
    channels = await db.get_all_channels()
    
    ch_list = ""
    for ch in channels:
        ch_list += f"• <code>{ch['channel_id']}</code> - {ch['name']}\n"
        
    await message.answer(
        f"Qaysi kanal uchun footer yozmoqchisiz? Kanal ID sini yuboring:\n\n{ch_list}",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.updating_footer_channel_select)
async def update_footer_channel_select(message: Message, state: FSMContext):
    try:
        channel_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID noto'g'ri. Raqamlardan iborat bo'lishi lozim.")
        return
        
    channel = await db.get_channel(channel_id)
    if not channel:
        await message.answer("❌ Bunday kanal topilmadi. Qayta urinib ko'ring.")
        return
        
    await state.update_data(footer_channel_id=channel_id)
    await state.set_state(AdminStates.updating_footer_text)
    
    current_footer = channel.get("footer_text", "")
    current_footer_str = f"\n\nJoriy footer:\n<i>{current_footer}</i>" if current_footer else "\nHali footer belgilanmagan."
    
    await message.answer(
        f"Kanal: <b>{channel['name']}</b>\n{current_footer_str}\n\n"
        "Yangi footer matnini yuboring (HTML formatlash qo'llab-quvvatlanadi). "
        "Footer ni o'chirish uchun <code>none</code> deb yozing.",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.updating_footer_text)
async def update_footer_text_process(message: Message, state: FSMContext):
    data = await state.get_data()
    channel_id = data.get("footer_channel_id")
    
    footer_text = message.html_text
    if footer_text.strip().lower() == "none":
        footer_text = ""
        
    await db.update_channel_footer(channel_id, footer_text)
    await state.clear()
    
    msg = "✅ Footer o'chirildi." if not footer_text else f"✅ Footer yangilandi:\n\n{footer_text}"
    await message.answer(msg, reply_markup=kb.get_channels_menu(), parse_mode="HTML")


# --- FORCE SUBSCRIPTION ---

@router.message(F.text == "🔄 Force Subscription")
async def force_sub_menu_handler(message: Message):
    await message.answer("🔄 Majburiy obunani boshqarish:", reply_markup=kb.get_force_sub_menu())


@router.message(F.text == "📋 Force Sub Channels")
async def force_sub_list_handler(message: Message):
    force_channels = await db.get_force_sub_channels()
    if not force_channels:
        await message.answer("Majburiy obuna kanallari belgilanmagan.")
        return
        
    msg = "🔒 <b>Majburiy obuna kanallari:</b>\n\n"
    for ch in force_channels:
        msg += f"• <b>{ch['name']}</b> (<code>{ch['channel_id']}</code>)\nHavola: {ch.get('invite_link', 'Mavjud emas')}\n\n"
    await message.answer(msg, parse_mode="HTML")


@router.message(F.text == "🔄 Toggle Channel Force Sub")
async def force_sub_toggle_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.force_sub_toggle)
    channels = await db.get_all_channels()
    
    ch_list = ""
    for ch in channels:
        status = "🔒 Majburiy" if ch.get("is_force_sub") else "🔓 Majburiy emas"
        ch_list += f"• <code>{ch['channel_id']}</code> - {ch['name']} (<b>{status}</b>)\n"
        
    await message.answer(
        f"Kanal ID sini yuboring (Obunani yoqish/o'chirish uchun):\n\n{ch_list}",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )

@router.message(AdminStates.force_sub_toggle)
async def force_sub_toggle_process(message: Message, state: FSMContext):
    try:
        channel_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ ID noto'g'ri. Raqamlardan iborat bo'lishi lozim.")
        return
        
    channel = await db.get_channel(channel_id)
    if not channel:
        await message.answer("❌ Bunday kanal topilmadi. Qayta urinib ko'ring.")
        return
        
    current_status = channel.get("is_force_sub", False)
    new_status = not current_status
    
    # Require invite link if enabling force sub
    if new_status and not channel.get("invite_link"):
        await message.answer("⚠️ Majburiy obunani yoqishdan oldin kanalga invite_link o'rnating. Ulanish havolasi yo'q.")
        # But we'll let it pass or require them to re-add with link
        
    await db.toggle_channel_force_sub(channel_id, new_status)
    await state.clear()
    
    status_str = "yoqildi" if new_status else "o'chirildi"
    await message.answer(
        f"✅ Kanal <b>{channel['name']}</b> uchun majburiy obuna statusi <b>{status_str}</b>.",
        reply_markup=kb.get_force_sub_menu(),
        parse_mode="HTML"
    )


# --- MANAGE ADMINS ---

@router.message(F.text == "👤 Manage Admins")
async def manage_admins_menu_handler(message: Message, db_user: dict):
    # Only owners can manage other admins
    if db_user.get("role") != "owner":
        await message.answer("❌ Adminlarni boshqarish faqat Asosiy Ega (Owner) uchun ruxsat etilgan.")
        return
    await message.answer("👤 Adminlarni boshqarish bo'limi:", reply_markup=kb.get_admins_menu())


@router.message(F.text == "📋 List Admins")
async def list_admins_handler(message: Message):
    admins = await db.get_admins()
    msg = "👤 <b>Bot Administratorlari ro'yxati:</b>\n\n"
    for adm in admins:
        msg += f"• <code>{adm['id']}</code> - Role: <b>{adm['role']}</b>\n"
    await message.answer(msg, parse_mode="HTML")


@router.message(F.text == "➕ Add Admin")
async def add_admin_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.adding_admin)
    await message.answer("Yangi admin Telegram ID sini yuboring:", reply_markup=kb.get_cancel_keyboard())

@router.message(AdminStates.adding_admin)
async def add_admin_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Telegram ID raqamlardan iborat bo'lishi lozim.")
        return
        
    user = await db.get_user(user_id)
    if not user:
        # Register user first
        await db.register_user(user_id, role="admin")
    else:
        if user["role"] == "owner":
            await message.answer("❌ Ushbu foydalanuvchi allaqachon bot egasi.")
            return
        await db.update_user_role(user_id, "admin")
        
    await state.clear()
    await message.answer(f"✅ Foydalanuvchi {user_id} bot admini etib tayinlandi.", reply_markup=kb.get_admins_menu())


@router.message(F.text == "➖ Remove Admin")
async def remove_admin_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.removing_admin)
    await message.answer("Chetlatmoqchi bo'lgan adminingiz Telegram ID sini yuboring:", reply_markup=kb.get_cancel_keyboard())

@router.message(AdminStates.removing_admin)
async def remove_admin_process(message: Message, state: FSMContext):
    try:
        user_id = int(message.text.strip())
    except ValueError:
        await message.answer("❌ Telegram ID raqamlardan iborat bo'lishi lozim.")
        return
        
    user = await db.get_user(user_id)
    if not user:
        await message.answer("❌ Foydalanuvchi bazadan topilmadi.")
        return
        
    if user["role"] == "owner":
        await message.answer("❌ Bot egasini adminlikdan olib tashlab bo'lmaydi.")
        return
        
    if user["role"] != "admin":
        await message.answer("❌ Ushbu foydalanuvchi admin emas.")
        return
        
    await db.update_user_role(user_id, "user")
    await state.clear()
    await message.answer(f"✅ Foydalanuvchi {user_id} adminlikdan chetlatildi.", reply_markup=kb.get_admins_menu())
