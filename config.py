import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/scheduler_bot")

# Parse numeric config values safely
try:
    OWNER_ID = int(os.getenv("OWNER_ID", "5924300834"))
except ValueError:
    OWNER_ID = 5924300834

try:
    DB_CHANNEL_ID = int(os.getenv("DB_CHANNEL_ID", "-1003977193789"))
except ValueError:
    DB_CHANNEL_ID = -1003977193789

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is not set in the environment or .env file.")
