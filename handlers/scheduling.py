import logging
import datetime
import uuid
import re
from typing import List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder

import config
import database.models as db
import keyboards.reply as kb
from states.states import PostCreationStates
from services.scheduler import scheduler, calculate_post_scheduled_time, schedule_post_jobs, timezone

logger = logging.getLogger(__name__)
router = Router()

# Helper to verify user is admin/owner
async def is_admin_filter(message: Message, db_user: dict = None) -> bool:
    if message.from_user.id == config.OWNER_ID:
        return True
    return db_user is not None and db_user.get("role") in ["admin", "owner"]

router.message.filter(is_admin_filter)


# --- QUEUE PREVIEW ---

@router.message(F.text == "👀 Navbatni ko'rish")
async def preview_queue_start(message: Message):
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("❌ Hali birorta kanal qo'shilmagan. Avval kanallarni boshqarish bo'limidan kanal qo'shing.")
        return
        
    preview_msg = "👀 <b>Navbatdagi Rejalashtirilgan Postlar (Kanal kesimida):</b>\n\n"
    post_types_uz = {
        "photo": "Rasm",
        "video": "Video",
        "document": "Hujjat",
        "audio": "Audio",
        "text": "Matn"
    }
    
    for ch in channels:
        ch_id = ch["channel_id"]
        queue = await db.get_queue_preview(ch_id, limit=3)
        
        preview_msg += f"📢 <b>Kanal: {ch['name']}</b> (<code>{ch_id}</code>)\n"
        if not queue:
            preview_msg += "  <i>Kutilayotgan postlar mavjud emas.</i>\n\n"
            continue
            
        for i, post in enumerate(queue, 1):
            scheduled_time = post["scheduled_time"]
            if scheduled_time.tzinfo is None:
                scheduled_time = timezone.localize(scheduled_time)
            
            # Format time beautifully
            time_str = scheduled_time.strftime("%Y-%m-%d %H:%M:%S")
            
            clean_text = re.sub(r'<[^>]+>', '', post["text"])
            text_snippet = clean_text[:60] + "..." if len(clean_text) > 60 else clean_text
            if not text_snippet.strip():
                p_type = post["type"]
                type_uz = post_types_uz.get(p_type, p_type.upper())
                text_snippet = f"[Fayl: {type_uz}]"
                
            p_type = post["type"]
            type_uz = post_types_uz.get(p_type, p_type.upper())
            preview_msg += (
                f"  {i}. ID: <code>{post['post_id']}</code>\n"
                f"     Turi: <b>{type_uz}</b>\n"
                f"     Vaqt: <code>{time_str}</code>\n"
                f"     Matn: <i>{text_snippet}</i>\n"
            )
        preview_msg += "\n"
        
    await message.answer(preview_msg, parse_mode="HTML")


# --- POST CREATION FLOW ---

@router.message(F.text == "📅 Post rejalashtirish")
async def schedule_post_start(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(custom_footer=None)
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("❌ Kanallar mavjud emas! Avval kanallarni boshqarish bo'limidan kanal qo'shing.")
        return
        
    # Build reply keyboard containing target channels list dynamically
    builder = ReplyKeyboardBuilder()
    for ch in channels:
        builder.row(KeyboardButton(text=f"{ch['name']} ({ch['channel_id']})"))
    builder.row(KeyboardButton(text="❌ Bekor qilish"))
    
    await state.set_state(PostCreationStates.waiting_for_channel)
    await message.answer(
        "Qaysi kanalga postlarni joylamoqchisiz? Quyidagi kanallardan birini tanlang:",
        reply_markup=builder.as_markup(resize_keyboard=True)
    )


@router.message(PostCreationStates.waiting_for_channel)
async def channel_selected_process(message: Message, state: FSMContext):
    # Match the channel ID inside the parentheses (e.g. "Channel Name (-100123456)")
    match = re.search(r"\((-\d+)\)", message.text)
    if not match:
        await message.answer("❌ Noto'g'ri kanal tanlandi. Iltimos quyidagi tugmalardan foydalaning.")
        return
        
    channel_id = int(match.group(1))
    channel = await db.get_channel(channel_id)
    if not channel:
        await message.answer("❌ Kanal ma'lumotlar bazasida topilmadi. Qayta urinib ko'ring.")
        return
        
    # Initialize the temp batch cache list inside state
    await state.update_data(target_channel=channel_id, temp_batch=[])
    await state.set_state(PostCreationStates.waiting_for_media_batch)
    await message.answer(
        f"📢 Tanlangan kanal: <b>{channel['name']}</b>\n\n"
        "Endi ushbu botga bir yoki bir nechta postlarni yuboring (matn, rasm, video, audio yoki fayllar) yoki ularni kanaldan forward qiling.\n\n"
        "Barcha postlarni yuborib bo'lgach, <b>✅ Yuklashni yakunlash</b> tugmasini bosing.",
        reply_markup=kb.get_ingestion_keyboard(),
        parse_mode="HTML"
    )


# Handle incoming ingestion messages
@router.message(PostCreationStates.waiting_for_media_batch, ~F.text.in_(["✅ Yuklashni yakunlash", "❌ Bekor qilish"]))
async def process_forwarded_posts(message: Message, state: FSMContext):
    # Retrieve existing temp batch list
    data = await state.get_data()
    temp_batch = data.get("temp_batch", [])
    
    # Analyze message type and extract file_id
    file_id = None
    media_type = "text"
    caption = ""
    
    if message.photo:
        media_type = "photo"
        file_id = message.photo[-1].file_id
        caption = message.html_text or ""
    elif message.video:
        media_type = "video"
        file_id = message.video.file_id
        caption = message.html_text or ""
    elif message.document:
        media_type = "document"
        file_id = message.document.file_id
        caption = message.html_text or ""
    elif message.audio:
        media_type = "audio"
        file_id = message.audio.file_id
        caption = message.html_text or ""
    elif message.text:
        media_type = "text"
        caption = message.html_text or ""
    else:
        # Unsupported format, skip it silently as per requirements (no status spam)
        return
        
    # Append post metadata
    temp_batch.append({
        "message_id": message.message_id,
        "file_id": file_id,
        "media_type": media_type,
        "caption": caption
    })
    
    await state.update_data(temp_batch=temp_batch)


@router.message(PostCreationStates.waiting_for_media_batch, F.text == "✅ Yuklashni yakunlash")
async def ingestion_done_process(message: Message, state: FSMContext):
    data = await state.get_data()
    temp_batch = data.get("temp_batch", [])
    target_channel = data.get("target_channel")
    
    if not temp_batch:
        await message.answer("❌ Hech qanday post yuborilmadi! Kamida bitta post yuborishingiz kerak.")
        return
        
    # Sort the cached temp_batch explicitly by Telegram's native message.message_id
    temp_batch.sort(key=lambda x: x["message_id"])
    
    # Generate unique batch ID
    batch_id = str(uuid.uuid4())
    
    # Update FSM state data
    await state.update_data(temp_batch=temp_batch, batch_id=batch_id)
    await state.set_state(PostCreationStates.waiting_for_custom_footer)
    
    await message.answer(
        "Ushbu rejalashtirilayotgan postlar to'plami uchun maxsus footer (matn tagidagi havola/reklama) qo'shishni xohlaysizmi? Footer matnini yuboring yoki o'tkazib yuborish uchun /skip bosing.",
        reply_markup=kb.get_footer_skip_keyboard(),
        parse_mode="HTML"
    )


@router.message(PostCreationStates.waiting_for_custom_footer)
async def custom_footer_process(message: Message, state: FSMContext):
    input_text = message.text.strip() if message.text else ""
    
    if input_text.lower() in ["/skip", "⏭️ o'tkazib yuborish"]:
        custom_footer = None
    else:
        # Preserve HTML formatting
        custom_footer = message.html_text or message.text or None
        
    data = await state.get_data()
    temp_batch = data.get("temp_batch", [])
    target_channel = data.get("target_channel")
    batch_id = data.get("batch_id")
    
    post_ids = []
    # Save the posts with the custom footer to MongoDB as drafts
    for item in temp_batch:
        post_id = str(uuid.uuid4())
        await db.create_post(
            post_id=post_id,
            file_id=item["file_id"],
            text=item["caption"],
            post_type=item["media_type"],
            target_channel=target_channel,
            status="draft",
            caption=item["caption"],
            media_type=item["media_type"],
            batch_id=batch_id,
            custom_footer=custom_footer
        )
        post_ids.append(post_id)
        
    await state.update_data(temp_batch=[], post_ids=post_ids, custom_footer=custom_footer)
    
    await state.set_state(PostCreationStates.waiting_for_schedule_mode)
    await message.answer(
        f"✅ Jami <b>{len(post_ids)}</b> ta post muvaffaqiyatli yuklandi.\n\n"
        "Endi rejalashtirish rejimini tanlang:",
        reply_markup=kb.get_schedule_mode_keyboard(),
        parse_mode="HTML"
    )


# --- SCHEDULING CONFIGURATION ---

@router.message(PostCreationStates.waiting_for_schedule_mode)
async def schedule_mode_selected(message: Message, state: FSMContext):
    mode_text = message.text
    mode_map = {
        "⏰ Har kuni (Belgilangan vaqtda)": "fixed",
        "⏳ Har N kunda": "interval",
        "🎲 Tasodifiy vaqt oralig'ida": "random",
        "🔄 Doimiy har kuni": "daily_infinite",
        "🔄 Navbatma-navbat aylantirish": "rotation"
    }
    
    if mode_text not in mode_map:
        await message.answer("❌ Noto'g'ri rejim. Iltimos tugmalardan birini tanlang.")
        return
        
    mode = mode_map[mode_text]
    await state.update_data(schedule_mode=mode)
    await state.set_state(PostCreationStates.waiting_for_schedule_time)
    
    if mode in ["fixed", "daily_infinite", "rotation"]:
        await message.answer(
            "Har kuni qaysi vaqtda yuborilsin? Format: <code>HH:MM</code> (masalan: <code>18:30</code>)",
            reply_markup=kb.get_cancel_keyboard(),
            parse_mode="HTML"
        )
    elif mode == "interval":
        await message.answer(
            "Har necha kunda va qaysi vaqtda yuborilsin? Format: <code>N HH:MM</code> (masalan: <code>2 15:00</code> - har 2 kunda soat 15:00 da)",
            reply_markup=kb.get_cancel_keyboard(),
            parse_mode="HTML"
        )
    elif mode == "random":
        await message.answer(
            "Qaysi vaqt oralig'ida tasodifiy vaqtda yuborilsin? Format: <code>HH:MM-HH:MM</code> (masalan: <code>14:00-17:00</code>)",
            reply_markup=kb.get_cancel_keyboard(),
            parse_mode="HTML"
        )


@router.message(PostCreationStates.waiting_for_schedule_time)
async def schedule_time_process(message: Message, state: FSMContext):
    data = await state.get_data()
    mode = data.get("schedule_mode")
    input_text = message.text.strip()
    
    schedule_config = {"mode": mode}
    
    # Validation regex
    time_regex = r"^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$"
    
    if mode in ["fixed", "daily_infinite", "rotation"]:
        if not re.match(time_regex, input_text):
            await message.answer("❌ Noto'g'ri vaqt formati. Format: <code>HH:MM</code> (00:00 - 23:59)", parse_mode="HTML")
            return
        schedule_config["time"] = input_text
        
    elif mode == "interval":
        parts = input_text.split()
        if len(parts) != 2:
            await message.answer("❌ Xato format. Format: <code>N HH:MM</code> (masalan: <code>2 15:00</code>)", parse_mode="HTML")
            return
        try:
            n_days = int(parts[0])
            if n_days <= 0:
                raise ValueError()
        except ValueError:
            await message.answer("❌ N kun musbat butun son bo'lishi lozim.")
            return
            
        time_part = parts[1]
        if not re.match(time_regex, time_part):
            await message.answer("❌ Noto'g'ri vaqt formati. Format: <code>HH:MM</code>", parse_mode="HTML")
            return
            
        schedule_config["interval_days"] = n_days
        schedule_config["time"] = time_part
        
    elif mode == "random":
        parts = input_text.split("-")
        if len(parts) != 2:
            await message.answer("❌ Xato format. Format: <code>HH:MM-HH:MM</code> (masalan: <code>14:00-17:00</code>)", parse_mode="HTML")
            return
            
        if not re.match(time_regex, parts[0]) or not re.match(time_regex, parts[1]):
            await message.answer("❌ Noto'g'ri vaqt chegaralari. Format: <code>HH:MM-HH:MM</code>", parse_mode="HTML")
            return
            
        schedule_config["random_window"] = {"start": parts[0], "end": parts[1]}
        
    await state.update_data(schedule_config=schedule_config)
    await state.set_state(PostCreationStates.waiting_for_reminders)
    await message.answer(
        "Post yuborilishidan oldin ogohlantirish (reminder) yuborilsinmi?\n\n"
        "Daqiqalarni vergul bilan ajratib kiriting (masalan: <code>30,15,5</code> - postdan 30, 15 va 5 daqiqa oldin xabar yuboriladi).\n"
        "Ogohlantirish kerak bo'lmasa, <code>none</code> deb yozing.",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(PostCreationStates.waiting_for_reminders)
async def reminders_process(message: Message, state: FSMContext):
    input_text = message.text.strip().lower()
    reminders = []
    
    if input_text != "none":
        parts = input_text.split(",")
        for p in parts:
            try:
                mins = int(p.strip())
                if mins <= 0:
                    raise ValueError()
                reminders.append(mins)
            except ValueError:
                await message.answer("❌ Xato format. Daqiqalar musbat butun son bo'lishi lozim (masalan: 30,15,5).")
                return
                
    # Sort reminders descending (e.g. 30 then 15 then 5)
    reminders.sort(reverse=True)
    
    # Retrieve all inputs
    data = await state.get_data()
    post_ids = data.get("post_ids", [])
    schedule_config = data.get("schedule_config", {})
    mode = schedule_config.get("mode")
    
    # Store reminders list inside schedule_config and empty reactions list
    schedule_config["reminders"] = reminders
    schedule_config["reactions"] = []
    
    now = datetime.datetime.now(timezone)
    
    await message.answer("🔄 Postlar rejalashtirilmoqda, iltimos kuting...")
    
    # Iterate through draft posts sequentially updating them in MongoDB and creating APScheduler jobs
    for i, post_id in enumerate(post_ids):
        if mode == "rotation":
            if i == 0:
                # The first post is pending and scheduled
                scheduled_time = calculate_post_scheduled_time(schedule_config, 0, now_time=now)
                status = "pending"
            else:
                scheduled_time = None
                status = "rotation_waiting"
        else:
            scheduled_time = calculate_post_scheduled_time(schedule_config, i, now_time=now)
            status = "pending"
            
        await db.get_posts_col().update_one(
            {"post_id": post_id},
            {
                "$set": {
                    "schedule_config": schedule_config,
                    "status": status,
                    "sequence_index": i
                }
            }
        )
        if scheduled_time is not None:
            await db.get_posts_col().update_one(
                {"post_id": post_id},
                {"$set": {"scheduled_time": scheduled_time}}
            )
            
        # Register in APScheduler (only if status is pending)
        if status == "pending" and scheduled_time is not None:
            schedule_post_jobs(post_id, scheduled_time, reminders)
            
    await state.clear()
    
    # Show main admin menu and confirmation
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer(
        f"✅ <b>Muvaffaqiyatli rejalashtirildi!</b>\n\n"
        f"Jami: <b>{len(post_ids)}</b> ta post navbatga qo'shildi.\n"
        "Postlar belgilangan vaqt bo'yicha ketma-ket yuboriladi.",
        reply_markup=kb.get_admin_menu(global_pause),
        parse_mode="HTML"
    )
