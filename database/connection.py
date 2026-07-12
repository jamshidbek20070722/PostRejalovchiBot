import logging
from motor.motor_asyncio import AsyncIOMotorClient
import config

logger = logging.getLogger(__name__)

class DatabaseConnection:
    def __init__(self):
        self.client = None
        self.db = None

    def connect(self):
        if self.client is None:
            logger.info("Connecting to MongoDB...")
            self.client = AsyncIOMotorClient(config.MONGO_URI)
            # Enforce the standard database name identifier
            db_name = "PostRejalovchiDB"
            self.db = self.client[db_name]
            logger.info(f"Connected to database: {db_name}")
        return self.db

    async def check_connection(self) -> bool:
        try:
            self.connect()
            # The ping command is cheap and checks if the server is available
            await self.db.command("ping")
            return True
        except Exception as e:
            logger.error(f"MongoDB connection check failed: {e}")
            return False

    def get_db(self):
        if self.db is None:
            self.connect()
        return self.db

# Global database manager instance
db_manager = DatabaseConnection()
