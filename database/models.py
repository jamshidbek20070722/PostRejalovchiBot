import datetime
from typing import List, Dict, Any, Optional
from database.connection import db_manager

# Collections getters helper
def get_users_col():
    return db_manager.get_db()["users"]

def get_channels_col():
    return db_manager.get_db()["channels"]

def get_posts_col():
    return db_manager.get_db()["posts"]

def get_reactions_col():
    return db_manager.get_db()["reactions"]

def get_settings_col():
    return db_manager.get_db()["settings"]


# --- USER OPERATIONS ---

async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    return await get_users_col().find_one({"id": user_id})

async def register_user(user_id: int, role: str = "user") -> Dict[str, Any]:
    existing = await get_user(user_id)
    if existing:
        return existing
    
    user_doc = {
        "id": user_id,
        "role": role,
        "joined_date": datetime.datetime.now(datetime.timezone.utc)
    }
    await get_users_col().insert_one(user_doc)
    return user_doc

async def update_user_role(user_id: int, role: str) -> bool:
    res = await get_users_col().update_one({"id": user_id}, {"$set": {"role": role}})
    return res.modified_count > 0

async def get_admins() -> List[Dict[str, Any]]:
    cursor = get_users_col().find({"role": {"$in": ["admin", "owner"]}})
    return await cursor.to_list(length=100)

async def get_user_stats() -> Dict[str, Any]:
    total_users = await get_users_col().count_documents({})
    admins_count = await get_users_col().count_documents({"role": "admin"})
    owners_count = await get_users_col().count_documents({"role": "owner"})
    return {
        "total_users": total_users,
        "admins": admins_count,
        "owners": owners_count
    }


# --- CHANNEL OPERATIONS ---

async def get_channel(channel_id: int) -> Optional[Dict[str, Any]]:
    return await get_channels_col().find_one({"channel_id": channel_id})

async def add_channel(channel_id: int, name: str, invite_link: str = "") -> bool:
    existing = await get_channel(channel_id)
    if existing:
        await get_channels_col().update_one(
            {"channel_id": channel_id},
            {"$set": {"name": name, "invite_link": invite_link}}
        )
        return True
    
    channel_doc = {
        "channel_id": channel_id,
        "name": name,
        "footer_text": "",
        "is_force_sub": False,
        "invite_link": invite_link
    }
    await get_channels_col().insert_one(channel_doc)
    return True

async def remove_channel(channel_id: int) -> bool:
    res = await get_channels_col().delete_one({"channel_id": channel_id})
    return res.deleted_count > 0

async def get_all_channels() -> List[Dict[str, Any]]:
    cursor = get_channels_col().find({})
    return await cursor.to_list(length=100)

async def get_force_sub_channels() -> List[Dict[str, Any]]:
    cursor = get_channels_col().find({"is_force_sub": True})
    return await cursor.to_list(length=100)

async def update_channel_footer(channel_id: int, footer_text: str) -> bool:
    res = await get_channels_col().update_one(
        {"channel_id": channel_id},
        {"$set": {"footer_text": footer_text}}
    )
    return res.modified_count > 0

async def toggle_channel_force_sub(channel_id: int, is_force_sub: bool) -> bool:
    res = await get_channels_col().update_one(
        {"channel_id": channel_id},
        {"$set": {"is_force_sub": is_force_sub}}
    )
    return res.modified_count > 0


# --- POST OPERATIONS ---

async def create_post(
    post_id: str,
    file_id: Optional[str],
    text: str,
    post_type: str,
    target_channel: int,
    schedule_config: Optional[Dict[str, Any]] = None,
    scheduled_time: Optional[datetime.datetime] = None,
    status: str = "pending",
    caption: Optional[str] = None,
    media_type: Optional[str] = None,
    batch_id: Optional[str] = None
) -> bool:
    post_doc = {
        "post_id": post_id,
        "file_id": file_id,
        "text": text,
        "caption": caption if caption is not None else text,
        "type": post_type,
        "media_type": media_type if media_type is not None else post_type,
        "target_channel": target_channel,
        "status": status,
        "created_at": datetime.datetime.now(datetime.timezone.utc)
    }
    if schedule_config is not None:
        post_doc["schedule_config"] = schedule_config
    if scheduled_time is not None:
        post_doc["scheduled_time"] = scheduled_time
    if batch_id is not None:
        post_doc["batch_id"] = batch_id
        
    await get_posts_col().insert_one(post_doc)
    return True

async def get_post(post_id: str) -> Optional[Dict[str, Any]]:
    return await get_posts_col().find_one({"post_id": post_id})

async def update_post_status(post_id: str, status: str) -> bool:
    res = await get_posts_col().update_one({"post_id": post_id}, {"$set": {"status": status}})
    return res.modified_count > 0

async def get_pending_posts() -> List[Dict[str, Any]]:
    cursor = get_posts_col().find({"status": "pending"})
    return await cursor.to_list(length=1000)

async def get_queue_preview(channel_id: int, limit: int = 3) -> List[Dict[str, Any]]:
    cursor = get_posts_col().find(
        {"target_channel": channel_id, "status": "pending"}
    ).sort("scheduled_time", 1).limit(limit)
    return await cursor.to_list(length=limit)

async def delete_post(post_id: str) -> bool:
    res = await get_posts_col().delete_one({"post_id": post_id})
    return res.deleted_count > 0

async def get_post_stats() -> Dict[str, Any]:
    total = await get_posts_col().count_documents({})
    pending = await get_posts_col().count_documents({"status": "pending"})
    posted = await get_posts_col().count_documents({"status": "posted"})
    failed = await get_posts_col().count_documents({"status": "failed"})
    paused = await get_posts_col().count_documents({"status": "paused"})
    return {
        "total": total,
        "pending": pending,
        "posted": posted,
        "failed": failed,
        "paused": paused
    }


# --- REACTION OPERATIONS ---

async def add_or_update_reaction(
    channel_id: int,
    message_id: int,
    user_id: int,
    reaction_type: str
) -> Optional[str]:
    """
    Registers a user's reaction.
    Returns:
      - None if user selected a new reaction
      - 'removed' if clicking same reaction to undo
      - 'updated' if switching from one reaction to another
    """
    query = {"channel_id": channel_id, "message_id": message_id, "user_id": user_id}
    existing = await get_reactions_col().find_one(query)
    
    if existing:
        if existing["reaction_type"] == reaction_type:
            # Clicked same reaction, toggle off (delete)
            await get_reactions_col().delete_one(query)
            return "removed"
        else:
            # Changed reaction
            await get_reactions_col().update_one(query, {"$set": {"reaction_type": reaction_type}})
            return "updated"
    else:
        # New reaction
        await get_reactions_col().insert_one({
            "channel_id": channel_id,
            "message_id": message_id,
            "user_id": user_id,
            "reaction_type": reaction_type,
            "timestamp": datetime.datetime.now(datetime.timezone.utc)
        })
        return "new"

async def get_reaction_counts(channel_id: int, message_id: int) -> Dict[str, int]:
    pipeline = [
        {"$match": {"channel_id": channel_id, "message_id": message_id}},
        {"$group": {"_id": "$reaction_type", "count": {"$sum": 1}}}
    ]
    cursor = get_reactions_col().aggregate(pipeline)
    results = await cursor.to_list(length=100)
    return {item["_id"]: item["count"] for item in results}


# --- SETTINGS / GLOBAL PAUSE OPERATIONS ---

async def set_global_setting(key: str, value: Any) -> bool:
    await get_settings_col().update_one(
        {"key": key},
        {"$set": {"value": value}},
        upsert=True
    )
    return True

async def get_global_setting(key: str, default: Any = None) -> Any:
    doc = await get_settings_col().find_one({"key": key})
    if doc:
        return doc["value"]
    return default
