import logging
from motor.motor_asyncio import AsyncIOMotorClient
import config

import certifi

logger = logging.getLogger(__name__)

class DatabaseConnection:
    def __init__(self):
        self.client = None
        self.db = None

    def connect(self):
        if self.client is None:
            logger.info("Connecting to MongoDB...")
            self.client = AsyncIOMotorClient(config.MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000)
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
            logger.warning(f"MongoDB secure connection check failed: {e}. Trying fallback with tlsAllowInvalidCertificates=True...")
            try:
                # Re-initialize client with disabled TLS certificate validation
                self.client = AsyncIOMotorClient(config.MONGO_URI, tlsAllowInvalidCertificates=True, serverSelectionTimeoutMS=5000)
                db_name = "PostRejalovchiDB"
                self.db = self.client[db_name]
                await self.db.command("ping")
                logger.info("Connected to MongoDB using fallback (tlsAllowInvalidCertificates=True).")
                return True
            except Exception as fallback_err:
                logger.error(f"MongoDB connection check failed on both standard and fallback attempts: {fallback_err}")
                return False

    def get_db(self):
        if self.db is None:
            self.connect()
        return self.db

# Global database manager instance
db_manager = DatabaseConnection()
