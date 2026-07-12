import logging
import datetime
import uuid
import re
from typing import List, Dict, Any

from aiogram import Router, F
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import ReplyKeyboardBuilder

import database.models as db
import keyboards.reply as kb
from states.states import PostCreationStates
from services.scheduler import scheduler, calculate_next_delivery_time, schedule_post_jobs, timezone

logger = logging.getLogger(__name__)
router = Router()

# Helper to verify user is admin/owner
async def is_admin_filter(message: Message, db_user: dict) -> bool:
    return db_user.get("role") in ["admin", "owner"]

router.message.filter(is_admin_filter)


# --- QUEUE PREVIEW ---

@router.message(F.text == "👀 Preview Queue")
async def preview_queue_start(message: Message):
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("❌ Hali birorta kanal qo'shilmagan. Avval kanallarni boshqarish bo'limidan kanal qo'shing.")
        return
        
    preview_msg = "👀 <b>Navbatdagi Rejalashtirilgan Postlar (Kanal kesimida):</b>\n\n"
    
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
            
            text_snippet = post["text"][:60] + "..." if len(post["text"]) > 60 else post["text"]
            if not text_snippet.strip():
                text_snippet = f"[Fayl: {post['type'].capitalize()}]"
                
            preview_msg += (
                f"  {i}. ID: <code>{post['post_id']}</code>\n"
                f"     Turi: <b>{post['type'].upper()}</b>\n"
                f"     Vaqt: <code>{time_str}</code>\n"
                f"     Matn: <i>{text_snippet}</i>\n"
            )
        preview_msg += "\n"
        
    await message.answer(preview_msg, parse_mode="HTML")


# --- POST CREATION FLOW ---

@router.message(F.text == "➕ Schedule Post")
async def schedule_post_start(message: Message, state: FSMContext):
    channels = await db.get_all_channels()
    if not channels:
        await message.answer("❌ Kanallar mavjud emas! Avval kanallarni boshqarish bo'limidan kanal qo'shing.")
        return
        
    # Build reply keyboard containing target channels list dynamically
    builder = ReplyKeyboardBuilder()
    for ch in channels:
        builder.row(KeyboardButton(text=f"{ch['name']} ({ch['channel_id']})"))
    builder.row(KeyboardButton(text="❌ Cancel"))
    
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
        
    await state.update_data(target_channel=channel_id, posts=[])
    await state.set_state(PostCreationStates.waiting_for_forwarded_posts)
    await message.answer(
        f"📢 Tanlangan kanal: <b>{channel['name']}</b>\n\n"
        "Endi ushbu botga bir yoki bir nechta postlarni yuboring (matn, rasm, video, audio yoki fayllar) yoki ularni kanaldan forward qiling.\n\n"
        "Barcha postlarni yuborib bo'lgach, <b>📥 Done Ingesting</b> tugmasini bosing.",
        reply_markup=kb.get_ingestion_keyboard(),
        parse_mode="HTML"
    )


# Handle incoming ingestion messages
@router.message(PostCreationStates.waiting_for_forwarded_posts, F.text != "📥 Done Ingesting")
async def process_forwarded_posts(message: Message, state: FSMContext):
    # Retrieve existing posts batch list
    data = await state.get_data()
    posts_list = data.get("posts", [])
    
    # Analyze message type and extract file_id
    file_id = None
    post_type = "text"
    text = ""
    
    if message.text:
        post_type = "text"
        text = message.html_text
    elif message.photo:
        post_type = "photo"
        file_id = message.photo[-1].file_id
        text = message.html_text or ""
    elif message.video:
        post_type = "video"
        file_id = message.video.file_id
        text = message.html_text or ""
    elif message.document:
        post_type = "document"
        file_id = message.document.file_id
        text = message.html_text or ""
    elif message.audio:
        post_type = "audio"
        file_id = message.audio.file_id
        text = message.html_text or ""
    else:
        # Unsupported format, skip it
        await message.answer("⚠️ Ushbu post turi qo'llab-quvvatlanmaydi! Faqat matn, rasm, video, audio va fayllarni yuboring.")
        return
        
    # Append post
    posts_list.append({
        "file_id": file_id,
        "text": text,
        "type": post_type
    })
    
    await state.update_data(posts=posts_list)
    await message.answer(f"📥 Post qabul qilindi! (Jami navbatda: <b>{len(posts_list)}</b> ta).", parse_mode="HTML")


@router.message(PostCreationStates.waiting_for_forwarded_posts, F.text == "📥 Done Ingesting")
async def ingestion_done_process(message: Message, state: FSMContext):
    data = await state.get_data()
    posts_list = data.get("posts", [])
    
    if not posts_list:
        await message.answer("❌ Hech qanday post yuborilmadi! Kamida bitta post yuborishingiz kerak.")
        return
        
    await state.set_state(PostCreationStates.waiting_for_schedule_mode)
    await message.answer(
        f"✅ Jami <b>{len(posts_list)}</b> ta post muvaffaqiyatli yuklandi.\n\n"
        "Endi rejalashtirish rejimini tanlang:",
        reply_markup=kb.get_schedule_mode_keyboard(),
        parse_mode="HTML"
    )


# --- SCHEDULING CONFIGURATION ---

@router.message(PostCreationStates.waiting_for_schedule_mode)
async def schedule_mode_selected(message: Message, state: FSMContext):
    mode_text = message.text
    mode_map = {
        "⏰ Every Day (Fixed)": "fixed",
        "⏳ Every N Days": "interval",
        "🎲 Random Window": "random"
    }
    
    if mode_text not in mode_map:
        await message.answer("❌ Noto'g'ri rejim. Iltimos tugmalardan birini tanlang.")
        return
        
    mode = mode_map[mode_text]
    await state.update_data(schedule_mode=mode)
    await state.set_state(PostCreationStates.waiting_for_schedule_time)
    
    if mode == "fixed":
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
    
    if mode == "fixed":
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
    await state.update_data(reminders=reminders)
    
    await state.set_state(PostCreationStates.waiting_for_reactions)
    await message.answer(
        "Postga qanday reaksiya/rating tugmalari qo'shilsin?\n\n"
        "1. Emojilarni vergul bilan kiriting (masalan: <code>🔥,👍,❤️</code>)\n"
        "2. 1-5 Star yulduzchali reyting uchun <code>stars</code> deb yozing\n"
        "3. Reaksiyasiz yuborish uchun <code>none</code> deb kiriting.",
        reply_markup=kb.get_cancel_keyboard(),
        parse_mode="HTML"
    )


@router.message(PostCreationStates.waiting_for_reactions)
async def reactions_process(message: Message, state: FSMContext):
    input_text = message.text.strip()
    
    reactions = []
    if input_text.lower() == "stars":
        reactions = ["1", "2", "3", "4", "5"]
    elif input_text.lower() != "none":
        # Split by comma and strip whitespace
        reactions = [r.strip() for r in input_text.split(",") if r.strip()]
        # Simple verification that they are emoji or strings
        if not reactions:
            await message.answer("❌ Noto'g'ri format. Emojilarni vergul bilan yuboring.")
            return
            
    # Retrieve all inputs
    data = await state.get_data()
    posts_list = data.get("posts", [])
    target_channel = data.get("target_channel")
    schedule_config = data.get("schedule_config")
    reminders = data.get("reminders", [])
    
    # Store reactions list inside schedule_config
    schedule_config["reactions"] = reactions
    schedule_config["reminders"] = reminders
    
    # Create jobs and store in database
    # Staggering logic:
    # If multiple posts are uploaded, we schedule them sequentially.
    # For example, if mode is fixed "15:00", we calculate the next delivery time.
    # Post 1 will be scheduled for date D1 at 15:00.
    # Post 2 will be scheduled for date D2 (D1 + 1 day or N days) at 15:00.
    # Post 3 for D3, etc. This spaces them out perfectly.
    
    now = datetime.datetime.now(timezone)
    last_scheduled_time = None
    
    await message.answer("🔄 Postlar rejalashtirilmoqda, iltimos kuting...")
    
    for i, post_info in enumerate(posts_list):
        post_id = str(uuid.uuid4())
        
        # Stagger delivery times
        # For post 0, use now as base date.
        # For subsequent posts, use the previously calculated post's time.
        base_time = last_scheduled_time or now
        scheduled_time = calculate_next_delivery_time(schedule_config, last_time=base_time)
        
        # Save scheduled time to track staggering
        last_scheduled_time = scheduled_time
        
        # Create Post in MongoDB
        await db.create_post(
            post_id=post_id,
            file_id=post_info["file_id"],
            text=post_info["text"],
            post_type=post_info["type"],
            target_channel=target_channel,
            schedule_config=schedule_config,
            scheduled_time=scheduled_time
        )
        
        # Register in APScheduler (timezone aware)
        schedule_post_jobs(post_id, scheduled_time, reminders)
        
    await state.clear()
    
    # Show main admin menu and confirmation
    global_pause = await db.get_global_setting("global_pause", False)
    await message.answer(
        f"✅ <b>Muvaffaqiyatli rejalashtirildi!</b>\n\n"
        f"Jami: <b>{len(posts_list)}</b> ta post navbatga qo'shildi.\n"
        "Postlar belgilangan vaqt bo'yicha ketma-ket yuboriladi.",
        reply_markup=kb.get_admin_menu(global_pause),
        parse_mode="HTML"
    )
