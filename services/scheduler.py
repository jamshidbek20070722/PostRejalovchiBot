import logging
import datetime
import random
import pytz
from typing import List, Dict, Any, Optional
from uuid import uuid4
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.date import DateTrigger
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import config
import database.models as db

logger = logging.getLogger(__name__)

# Initialize the scheduler with default timezone (UTC or system timezone)
timezone = pytz.timezone("Asia/Tashkent")  # Using timezone relevant to the workspace local time +05:00
scheduler = AsyncIOScheduler(timezone=timezone)

# We store the bot instance here once initialized to use in jobs
_bot: Optional[Bot] = None

from keyboards.inline import get_reaction_keyboard



async def send_reminder_job(post_id: str, minutes_left: int):
    """
    APScheduler job that runs X minutes before a scheduled post.
    Notifies the bot owner/admins.
    """
    global _bot
    if not _bot:
        logger.error("Bot instance not set in scheduler.")
        return
        
    post = await db.get_post(post_id)
    if not post or post["status"] != "pending":
        return
        
    channel_id = post["target_channel"]
    channel = await db.get_channel(channel_id)
    channel_name = channel["name"] if channel else f"ID: {channel_id}"
    
    # Notify owner
    text_preview = post["text"][:100] + "..." if len(post["text"]) > 100 else post["text"]
    message = (
        f"🔔 <b>Yaqinlashayotgan post haqida ogohlantirish</b>\n\n"
        f"<code>{post_id}</code> ID ga ega post <b>{minutes_left} daqiqa</b> ichida kanalga yuboriladi!\n"
        f"Maqsadli kanal: <b>{channel_name}</b>\n"
        f"Ko'rinishi:\n<i>{text_preview}</i>"
    )
    
    try:
        await _bot.send_message(chat_id=config.OWNER_ID, text=message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Failed to send reminder to owner: {e}")


async def send_scheduled_post_job(post_id: str):
    """
    APScheduler job that publishes the post to the target channel.
    """
    global _bot
    if not _bot:
        logger.error("Bot instance not set in scheduler.")
        return
        
    # Check for global pause setting
    global_pause = await db.get_global_setting("global_pause", False)
    if global_pause:
        logger.info(f"Skipping scheduled post {post_id} due to global pause.")
        return
        
    post = await db.get_post(post_id)
    if not post or post["status"] != "pending":
        logger.info(f"Post {post_id} not found or status is not pending.")
        return
        
    channel_id = post["target_channel"]
    post_type = post["type"]
    file_id = post["file_id"]
    text = post["text"]
    
    # 1. Fetch channel and append custom footer if present
    channel = await db.get_channel(channel_id)
    footer = channel.get("footer_text", "") if channel else ""
    
    final_text = text
    if footer:
        final_text = f"{text}\n\n{footer}"
        
    # 2. Build reaction keyboard if configured
    # In schedule_config, we store the list of reaction emoji or stars
    reactions = post["schedule_config"].get("reactions", [])
    
    # Temporary placeholder keyboard (empty markup if no reactions)
    # We will build actual keyboard once we get the sent message ID.
    reply_markup = None
    
    # 3. Publish the post based on media type
    sent_msg = None
    try:
        if post_type == "text":
            sent_msg = await _bot.send_message(
                chat_id=channel_id,
                text=final_text,
                parse_mode="HTML",
                disable_web_page_preview=False
            )
        elif post_type == "photo":
            sent_msg = await _bot.send_photo(
                chat_id=channel_id,
                photo=file_id,
                caption=final_text,
                parse_mode="HTML"
            )
        elif post_type == "video":
            sent_msg = await _bot.send_video(
                chat_id=channel_id,
                video=file_id,
                caption=final_text,
                parse_mode="HTML"
            )
        elif post_type == "document":
            sent_msg = await _bot.send_document(
                chat_id=channel_id,
                document=file_id,
                caption=final_text,
                parse_mode="HTML"
            )
        elif post_type == "audio":
            sent_msg = await _bot.send_audio(
                chat_id=channel_id,
                audio=file_id,
                caption=final_text,
                parse_mode="HTML"
            )
            
        if sent_msg:
            # 4. Attach reaction keyboard if reactions are set
            if reactions:
                # Store message ID in reactions mapping or update post
                # Initially counts are 0
                counts = {r: 0 for r in reactions}
                reply_markup = get_reaction_keyboard(channel_id, sent_msg.message_id, reactions, counts)
                await _bot.edit_message_reply_markup(
                    chat_id=channel_id,
                    message_id=sent_msg.message_id,
                    reply_markup=reply_markup
                )
                
            # Update post status in database
            await db.update_post_status(post_id, "posted")
            # Update post document with the message ID in channel for reference
            await db.get_posts_col().update_one(
                {"post_id": post_id},
                {"$set": {"msg_id": sent_msg.message_id}}
            )
            logger.info(f"Successfully posted scheduled post {post_id} to channel {channel_id}")
            
    except Exception as e:
        logger.error(f"Failed to send scheduled post {post_id}: {e}")
        await db.update_post_status(post_id, "failed")


def schedule_post_jobs(post_id: str, scheduled_time: datetime.datetime, reminders: List[int]):
    """
    Adds posting and reminder jobs to the running APScheduler instance.
    """
    # 1. Main posting job
    job_id = f"post_{post_id}"
    # Remove existing jobs if any to avoid duplication
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        
    scheduler.add_job(
        send_scheduled_post_job,
        trigger=DateTrigger(run_date=scheduled_time, timezone=timezone),
        id=job_id,
        args=[post_id],
        misfire_grace_time=3600  # Run even if 1 hour late due to downtime
    )
    
    # 2. Reminder jobs
    for min_before in reminders:
        reminder_time = scheduled_time - datetime.timedelta(minutes=min_before)
        # Check if reminder time is in the future
        now = datetime.datetime.now(timezone)
        if reminder_time > now:
            rem_job_id = f"rem_{post_id}_{min_before}"
            if scheduler.get_job(rem_job_id):
                scheduler.remove_job(rem_job_id)
                
            scheduler.add_job(
                send_reminder_job,
                trigger=DateTrigger(run_date=reminder_time, timezone=timezone),
                id=rem_job_id,
                args=[post_id, min_before],
                misfire_grace_time=600
            )


async def init_scheduler(bot: Bot):
    """
    Initializes the scheduler, registers the bot instance, and reloads pending jobs from MongoDB.
    """
    global _bot
    _bot = bot
    
    # Check global pause setting
    global_pause = await db.get_global_setting("global_pause", False)
    
    # Start the scheduler
    if not scheduler.running:
        scheduler.start()
        logger.info("APScheduler started.")
        
    if global_pause:
        scheduler.pause()
        logger.info("APScheduler jobs paused globally by settings.")
    else:
        scheduler.resume()
        
    # Load all pending posts from DB and schedule them
    pending_posts = await db.get_pending_posts()
    logger.info(f"Loaded {len(pending_posts)} pending scheduled posts from DB.")
    
    now = datetime.datetime.now(timezone)
    for post in pending_posts:
        post_id = post["post_id"]
        sched_time = post["scheduled_time"]
        
        # Ensure scheduled_time has timezone
        if sched_time.tzinfo is None:
            sched_time = timezone.localize(sched_time)
            
        reminders = post["schedule_config"].get("reminders", [])
        
        if sched_time > now:
            schedule_post_jobs(post_id, sched_time, reminders)
            logger.debug(f"Rescheduled post {post_id} at {sched_time}")
        else:
            # Post was scheduled in the past during bot downtime.
            # Post it immediately, or mark as failed/pending to run.
            # To avoid flooding channels, we schedule them to post in 10-60 seconds.
            post_time = now + datetime.timedelta(seconds=15)
            schedule_post_jobs(post_id, post_time, [])
            logger.warning(f"Post {post_id} was scheduled in past ({sched_time}). Rescheduled for immediate delivery.")


def calculate_next_delivery_time(schedule_config: Dict[str, Any], last_time: Optional[datetime.datetime] = None) -> datetime.datetime:
    """
    Calculates the target delivery datetime based on the schedule_config.
    Supported modes:
    1. fixed: Everyday at a fixed time (HH:MM)
    2. interval: Every N days at a starting/specified time
    3. random: Random minute inside a specific window (e.g., 14:00 to 17:00)
    """
    now = datetime.datetime.now(timezone)
    mode = schedule_config.get("mode")
    
    if mode == "fixed":
        time_str = schedule_config.get("time", "12:00")
        hh, mm = map(int, time_str.split(":"))
        target = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now:
            target += datetime.timedelta(days=1)
        return target
        
    elif mode == "interval":
        interval_days = schedule_config.get("interval_days", 1)
        time_str = schedule_config.get("time", "12:00")
        hh, mm = map(int, time_str.split(":"))
        
        # Base date is starting from now or the last scheduled time
        base_date = last_time or now
        target = base_date.replace(hour=hh, minute=mm, second=0, microsecond=0)
        # Add interval days
        target += datetime.timedelta(days=interval_days)
        
        if target <= now:
            # Catch up to future
            while target <= now:
                target += datetime.timedelta(days=interval_days)
        return target
        
    elif mode == "random":
        # window example: {"start": "14:00", "end": "17:00"}
        window = schedule_config.get("random_window", {"start": "12:00", "end": "14:00"})
        start_hh, start_mm = map(int, window["start"].split(":"))
        end_hh, end_mm = map(int, window["end"].split(":"))
        
        # Find minutes bounds
        start_minutes = start_hh * 60 + start_mm
        end_minutes = end_hh * 60 + end_mm
        
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60  # Handle overnight window
            
        # Select random minute
        rand_minutes = random.randint(start_minutes, end_minutes)
        rand_hh = (rand_minutes // 60) % 24
        rand_mm = rand_minutes % 60
        
        # Build target for today or tomorrow
        target = now.replace(hour=rand_hh, minute=rand_mm, second=0, microsecond=0)
        
        # If random minutes rolled over or target is past, schedule tomorrow
        if target <= now or rand_minutes >= 24 * 60:
            target = (now + datetime.timedelta(days=1)).replace(hour=rand_hh, minute=rand_mm, second=0, microsecond=0)
            
        return target
        
    else:
        # Fallback to 5 minutes in future if type unknown
        return now + datetime.timedelta(minutes=5)


def calculate_post_scheduled_time(schedule_config: Dict[str, Any], index: int, now_time: Optional[datetime.datetime] = None) -> datetime.datetime:
    """
    Calculates the target delivery datetime for a post at the given index in a batch.
    Increments the base scheduled time sequentially using a timedelta factor.
    """
    if now_time is None:
        now_time = datetime.datetime.now(timezone)
    mode = schedule_config.get("mode")
    
    if mode == "fixed":
        time_str = schedule_config.get("time", "12:00")
        hh, mm = map(int, time_str.split(":"))
        target = now_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now_time:
            target += datetime.timedelta(days=1)
        # Stagger sequentially by adding 'index' days
        target += datetime.timedelta(days=index)
        return target
        
    elif mode == "interval":
        interval_days = schedule_config.get("interval_days", 1)
        time_str = schedule_config.get("time", "12:00")
        hh, mm = map(int, time_str.split(":"))
        target = now_time.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if target <= now_time:
            target += datetime.timedelta(days=interval_days)
        # Stagger sequentially by adding (index * interval_days) days
        target += datetime.timedelta(days=index * interval_days)
        return target
        
    elif mode == "random":
        window = schedule_config.get("random_window", {"start": "12:00", "end": "14:00"})
        start_hh, start_mm = map(int, window["start"].split(":"))
        end_hh, end_mm = map(int, window["end"].split(":"))
        
        start_minutes = start_hh * 60 + start_mm
        end_minutes = end_hh * 60 + end_mm
        
        if end_minutes <= start_minutes:
            end_minutes += 24 * 60  # Handle overnight window
            
        rand_minutes = random.randint(start_minutes, end_minutes)
        rand_hh = (rand_minutes // 60) % 24
        rand_mm = rand_minutes % 60
        
        # Base day for stagger is now_time + index days
        base_day = now_time + datetime.timedelta(days=index)
        target = base_day.replace(hour=rand_hh, minute=rand_mm, second=0, microsecond=0)
        
        # Adjust for rolling over
        if index == 0 and (target <= now_time or rand_minutes >= 24 * 60):
            target = (now_time + datetime.timedelta(days=1)).replace(hour=rand_hh, minute=rand_mm, second=0, microsecond=0)
        elif index > 0 and rand_minutes >= 24 * 60:
            target += datetime.timedelta(days=1)
            
        return target
        
    else:
        # Fallback stagger
        return now_time + datetime.timedelta(minutes=5 + index * 5)
