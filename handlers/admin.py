import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.filters import Filter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import keyboards.reply as kb
import database.models as db
from states.states import AdminStates
from services.scheduler import scheduler

logger = logging.getLogger(__name__)
router = Router()

# Custom Filter to check if user is admin/owner (strictly OWNER_ID)
async def is_admin_filter(message: Message, db_user: dict) -> bool:
    return message.from_user.id == config.OWNER_ID

# Apply Admin Filter to all routes in this router
router.message.filter(is_admin_filter)
router.callback_query.filter(lambda c: c.from_user.id == config.OWNER_ID)


# --- GENERAL NAVIGATION & CANCEL ---

@router.message(F.text == "❌ Bekor qilish")
async def cancel_state_handler(message: Message, state: FSMContext):
    data = await state.get_data()
    post_ids = data.get("post_ids", [])
    if post_ids:
        try:
            await db.get_posts_col().delete_many({"post_id": {"$in": post_ids}})
        except Exception as e:
            logger.error(f"Failed to delete draft posts on cancel: {e}")
            
    await state.clear()
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer("❌ Harakat bekor qilindi.", reply_markup=kb.get_admin_menu(global_pause))


@router.message(F.text == "🔙 Admin panelga qaytish")
async def back_to_admin_handler(message: Message, state: FSMContext):
    await state.clear()
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer("🔙 Admin panelga qaytildi.", reply_markup=kb.get_admin_menu(global_pause))


# --- BOT STATS ---

@router.message(F.text == "📊 Bot statistikasi")
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
        f"  • Ega: {user_stats['owners']}\n\n"
        f"📢 <b>Ulangan Kanallar:</b>\n"
        f"{channels_text}\n"
        f"📝 <b>Postlar holati:</b>\n"
        f"  • Umumiy: {post_stats['total']}\n"
        f"  • Kutilayotgan: {post_stats['pending']}\n"
        f"  • Yuborilgan: {post_stats['posted']}\n"
        f"  • O'chirib qo'yilgan (Pauza): {post_stats['paused']}\n"
        f"  • Xatolik: {post_stats['failed']}\n"
        f"  • Navbatma-navbat (Kutishdagi): {post_stats.get('rotation', 0)}\n"
    )
    await message.answer(stats_msg, parse_mode="HTML")


# --- EMERGENCY STOP (GLOBAL PAUSE) ---

@router.message(F.text.in_(["🚨 Favqulodda to'xtatish", "⏸️ Favqulodda to'xtatish", "▶️ Ishlarni davom ettirish"]))
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
            reply_markup=kb.get_submenu_keyboard(new_pause),
            parse_mode="HTML"
        )
    else:
        scheduler.resume()
        await db.get_posts_col().update_many({"status": "paused"}, {"$set": {"status": "pending"}})
        await message.answer(
            "✅ <b>Bot faoliyati tiklandi!</b>\n\n"
            "Tizim ishga tushirildi. Rejalashtirilgan postlar o'z vaqtida yuboriladi.",
            reply_markup=kb.get_submenu_keyboard(new_pause),
            parse_mode="HTML"
        )


@router.message(F.text == "⚙️ Qo'shimcha imkoniyatlar")
async def submenu_handler(message: Message):
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer("⚙️ Qo'shimcha imkoniyatlar bo'limi:", reply_markup=kb.get_submenu_keyboard(global_pause))


@router.message(F.text == "⬅️ Orqaga")
async def back_to_main_menu_handler(message: Message):
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer("🔙 Asosiy menuga qaytildi.", reply_markup=kb.get_admin_menu(global_pause))


@router.message(F.text == "📝 Rejalangan postlar")
async def scheduled_posts_list_handler(message: Message):
    import re
    pending = await db.get_pending_posts()
    if not pending:
        await message.answer("📝 Hali birorta post rejalashtirilmagan.")
        return
        
    from services.scheduler import timezone
    sorted_posts = []
    for post in pending:
        t = post["scheduled_time"]
        if t.tzinfo is None:
            t = timezone.localize(t)
        sorted_posts.append((t, post))
        
    sorted_posts.sort(key=lambda x: x[0])
    
    msg = "📝 <b>Rejalashtirilgan postlar ro'yxati (Yaqin orada yuboriladigan 10 tasi):</b>\n\n"
    
    mode_labels = {
        "fixed": "Bir martalik",
        "daily_infinite": "Doimiy",
        "rotation": "Navbatma-navbat",
        "interval": "N kunda",
        "random": "Tasodifiy"
    }
    
    channels_cache = {}
    for i, (sched_time, post) in enumerate(sorted_posts[:10], 1):
        ch_id = post["target_channel"]
        if ch_id not in channels_cache:
            channel_info = await db.get_channel(ch_id)
            if channel_info:
                ch_name = channel_info.get("name") or channel_info.get("invite_link") or f"ID: {ch_id}"
            else:
                ch_name = f"ID: {ch_id}"
            channels_cache[ch_id] = ch_name
            
        ch_name = channels_cache[ch_id]
        
        mode = post.get("schedule_config", {}).get("mode", "fixed")
        mode_uz = mode_labels.get(mode, "Bir martalik")
        
        time_str = sched_time.strftime("%d.%m.%Y %H:%M")
        
        msg += f"{i}. 📢 Kanal: {ch_name}\n"
        msg += f"🔄 Rejim: {mode_uz} | ⏰ Vaqt: {time_str}\n"
        msg += f"---\n"
        
    if len(sorted_posts) > 10:
        msg += f"\n<i>... va yana {len(sorted_posts) - 10} ta post bor.</i>\n"
        
    msg += "\n🔍 Post tafsilotlarini ko'rish, tahrirlash yoki o'chirish uchun quyidagi raqamlardan birini tanlang:"
    
    builder = InlineKeyboardBuilder()
    number_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
    for i, (sched_time, post) in enumerate(sorted_posts[:10], 1):
        label = number_emojis[i-1] if i-1 < len(number_emojis) else str(i)
        builder.add(InlineKeyboardButton(text=label, callback_data=f"select_post:{post['post_id']}"))
        
    builder.adjust(5)
    
    await message.answer(msg, parse_mode="HTML", reply_markup=builder.as_markup())


# Callback query to select a scheduled post for viewing
@router.callback_query(F.data.startswith("select_post:"))
async def select_post_callback(callback: CallbackQuery):
    post_id = callback.data.split(":")[1]
    post = await db.get_post(post_id)
    if not post:
        await callback.answer("❌ Post topilmadi!", show_alert=True)
        return
        
    post_type = post["type"]
    file_id = post["file_id"]
    text = post["text"]
    
    # Fetch target channel name
    ch_id = post["target_channel"]
    channel_info = await db.get_channel(ch_id)
    ch_name = channel_info.get("name") if channel_info else f"ID: {ch_id}"
    
    # Calculate execution time
    from services.scheduler import timezone
    sched_time = post["scheduled_time"]
    if sched_time.tzinfo is None:
        sched_time = timezone.localize(sched_time)
    time_str = sched_time.strftime("%d.%m.%Y %H:%M")
    
    mode_labels = {
        "fixed": "Bir martalik",
        "daily_infinite": "Doimiy",
        "rotation": "Navbatma-navbat",
        "interval": "N kunda",
        "random": "Tasodifiy"
    }
    mode = post.get("schedule_config", {}).get("mode", "fixed")
    mode_uz = mode_labels.get(mode, "Bir martalik")
    
    header = (
        f"📅 <b>Rejalashtirilgan post tafsilotlari:</b>\n"
        f"📢 Kanal: {ch_name}\n"
        f"🔄 Rejim: {mode_uz} | ⏰ Vaqt: {time_str}\n\n"
        f"📝 <b>Post matni/taglavhasi:</b>\n"
    )
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✏️ Matnni tahrirlash", callback_data=f"edit_post:{post_id}"),
        InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"confirm_delete_post:{post_id}")
    )
    builder.row(
        InlineKeyboardButton(text="🔙 Ro'yxatga qaytish", callback_data="back_to_scheduled_posts")
    )
    
    await callback.answer()
    
    # Send the post preview in admin chat
    if post_type == "text":
        await callback.message.answer(f"{header}{text}", parse_mode="HTML", reply_markup=builder.as_markup())
    elif post_type == "photo":
        await callback.message.answer_photo(photo=file_id, caption=f"{header}{text}"[:1024], parse_mode="HTML", reply_markup=builder.as_markup())
    elif post_type == "video":
        await callback.message.answer_video(video=file_id, caption=f"{header}{text}"[:1024], parse_mode="HTML", reply_markup=builder.as_markup())
    elif post_type == "document":
        await callback.message.answer_document(document=file_id, caption=f"{header}{text}"[:1024], parse_mode="HTML", reply_markup=builder.as_markup())
    elif post_type == "audio":
        await callback.message.answer_audio(audio=file_id, caption=f"{header}{text}"[:1024], parse_mode="HTML", reply_markup=builder.as_markup())


# Back to scheduled posts list callback
@router.callback_query(F.data == "back_to_scheduled_posts")
async def back_to_scheduled_posts_callback(callback: CallbackQuery):
    await callback.message.delete()
    # Trigger the list handler logic again
    await scheduled_posts_list_handler(callback.message)
    await callback.answer()


# Callback to enter text editing state
@router.callback_query(F.data.startswith("edit_post:"))
async def edit_post_callback(callback: CallbackQuery, state: FSMContext):
    post_id = callback.data.split(":")[1]
    
    # Verify post exists
    post = await db.get_post(post_id)
    if not post:
        await callback.answer("❌ Post topilmadi!", show_alert=True)
        return
        
    await state.set_state(AdminStates.AwaitingNewPostText)
    await state.update_data(editing_post_id=post_id)
    
    await callback.answer()
    await callback.message.answer(
        "✏️ Yangi post matnini yuboring (HTML formatlash qo'llab-quvvatlanadi):",
        reply_markup=kb.get_cancel_keyboard()
    )


# Message handler to process editing the post text
@router.message(AdminStates.AwaitingNewPostText)
async def edit_post_text_process(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data.get("editing_post_id")
    
    new_text = message.html_text or message.text or ""
    
    # Update post text and caption in MongoDB
    await db.get_posts_col().update_one(
        {"post_id": post_id},
        {"$set": {"text": new_text, "caption": new_text}}
    )
    
    await state.clear()
    
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer(
        "✅ Yangi matn muvaffaqiyatli saqlandi. Post yuborilayotganda yangi matn chop etiladi.",
        reply_markup=kb.get_admin_menu(global_pause)
    )


# Callback to prompt delete confirmation
@router.callback_query(F.data.startswith("confirm_delete_post:"))
async def confirm_delete_post_callback(callback: CallbackQuery):
    post_id = callback.data.split(":")[1]
    
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Ha", callback_data=f"delete_post:{post_id}"),
        InlineKeyboardButton(text="❌ Yo'q", callback_data=f"cancel_delete_post:{post_id}")
    )
    
    await callback.answer()
    
    confirm_text = "⚠️ Haqiqatan ham ushbu rejalashtirilgan postni o'chirishni xohlaysizmi?"
    if callback.message.text:
        await callback.message.edit_text(confirm_text, reply_markup=builder.as_markup())
    else:
        await callback.message.edit_caption(caption=confirm_text, reply_markup=builder.as_markup())


# Callback to cancel delete
@router.callback_query(F.data.startswith("cancel_delete_post:"))
async def cancel_delete_post_callback(callback: CallbackQuery):
    post_id = callback.data.split(":")[1]
    await callback.message.delete()
    # Go back to previewing the post
    # Build a simulated callback query to call select_post_callback
    callback.data = f"select_post:{post_id}"
    await select_post_callback(callback)


# Callback to execute delete post
@router.callback_query(F.data.startswith("delete_post:"))
async def delete_post_callback(callback: CallbackQuery):
    post_id = callback.data.split(":")[1]
    
    # 1. Delete from MongoDB
    await db.delete_post(post_id)
    
    # 2. Cancel scheduler jobs (posting + reminders)
    from services.scheduler import cancel_post_jobs
    cancel_post_jobs(post_id)
    
    await callback.answer("🗑 Post o'chirildi.", show_alert=True)
    await callback.message.delete()


# --- MANAGE CHANNELS NAVIGATION ---

@router.message(F.text == "📢 Kanallarni boshqarish")
async def manage_channels_menu_handler(message: Message):
    await message.answer("📢 Kanallarni boshqarish bo'limi:", reply_markup=kb.get_channels_menu())


# --- ADD CHANNEL ---

@router.message(F.text == "➕ Kanal qo'shish")
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

@router.message(F.text == "➖ Kanalni o'chirish")
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

@router.message(F.text == "📝 Taglavhani yangilash")
async def update_footer_start(message: Message, state: FSMContext):
    await state.set_state(AdminStates.updating_footer_channel_select)
    channels = await db.get_all_channels()
    
    ch_list = ""
    for ch in channels:
        ch_list += f"• <code>{ch['channel_id']}</code> - {ch['name']}\n"
        
    await message.answer(
        f"Qaysi kanal uchun taglavha yozmoqchisiz? Kanal ID sini yuboring:\n\n{ch_list}",
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
    current_footer_str = f"\n\nJoriy taglavha:\n<i>{current_footer}</i>" if current_footer else "\nHali taglavha belgilanmagan."
    
    await message.answer(
        f"Kanal: <b>{channel['name']}</b>\n{current_footer_str}\n\n"
        "Yangi taglavha matnini yuboring (HTML formatlash qo'llab-quvvatlanadi). "
        "Taglavhani o'chirish uchun <code>none</code> deb yozing.",
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
    
    msg = "✅ Taglavha o'chirildi." if not footer_text else f"✅ Taglavha yangilandi:\n\n{footer_text}"
    await message.answer(msg, reply_markup=kb.get_channels_menu(), parse_mode="HTML")


# --- FORCE SUBSCRIPTION ---

@router.message(F.text == "🔄 Majburiy obuna")
async def force_sub_menu_handler(message: Message):
    await message.answer("🔄 Majburiy obunani boshqarish:", reply_markup=kb.get_force_sub_menu())


@router.message(F.text == "📋 Majburiy obuna kanallari")
async def force_sub_list_handler(message: Message):
    force_channels = await db.get_force_sub_channels()
    if not force_channels:
        await message.answer("Majburiy obuna kanallari belgilanmagan.")
        return
        
    msg = "🔒 <b>Majburiy obuna kanallari:</b>\n\n"
    for ch in force_channels:
        msg += f"• <b>{ch['name']}</b> (<code>{ch['channel_id']}</code>)\nHavola: {ch.get('invite_link', 'Mavjud emas')}\n\n"
    await message.answer(msg, parse_mode="HTML")


@router.message(F.text == "🔄 Kanal obunasini o'zgartirish")
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
        
    await db.toggle_channel_force_sub(channel_id, new_status)
    await state.clear()
    
    status_str = "yoqildi" if new_status else "o'chirildi"
    await message.answer(
        f"✅ Kanal <b>{channel['name']}</b> uchun majburiy obuna statusi <b>{status_str}</b>.",
        reply_markup=kb.get_force_sub_menu(),
        parse_mode="HTML"
    )


# --- MANAGE ADMINS ---

@router.message(F.text == "👤 Adminlarni boshqarish")
async def manage_admins_menu_handler(message: Message, db_user: dict):
    # Only owners can manage other admins
    if db_user.get("role") != "owner":
        await message.answer("❌ Adminlarni boshqarish faqat Asosiy Ega (Owner) uchun ruxsat etilgan.")
        return
    await message.answer("👤 Adminlarni boshqarish bo'limi:", reply_markup=kb.get_admins_menu())


@router.message(F.text == "📋 Adminlar ro'yxati")
async def list_admins_handler(message: Message):
    admins = await db.get_admins()
    msg = "👤 <b>Bot Administratorlari ro'yxati:</b>\n\n"
    for adm in admins:
        msg += f"• <code>{adm['id']}</code> - Rol: <b>{adm['role']}</b>\n"
    await message.answer(msg, parse_mode="HTML")


@router.message(F.text == "➕ Admin qo'shish")
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


@router.message(F.text == "➖ Adminni o'chirish")
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
