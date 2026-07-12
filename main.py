import asyncio
import logging
import sys
import os
from aiohttp import web

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

import config
from database.connection import db_manager
from middlewares.register_user import RegisterUserMiddleware
from middlewares.force_sub import ForceSubscriptionMiddleware
from handlers.user import router as user_router
from handlers.admin import router as admin_router
from handlers.scheduling import router as scheduling_router
from handlers.reaction import router as reaction_router
from services.scheduler import init_scheduler, scheduler

# Configure logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_health_server():
    port = int(os.getenv("PORT", "8080"))
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health check server started on port {port}")

async def main():
    logger.info("Starting Telegram Bot application...")
    
    # Start web health server if PORT is defined (e.g. on Railway)
    if os.getenv("PORT"):
        await start_health_server()
    
    # 1. Initialize MongoDB Connection
    db_connected = await db_manager.check_connection()
    if not db_connected:
        logger.critical("Could not connect to MongoDB. Exiting.")
        sys.exit(1)
        
    # 2. Initialize Bot and Dispatcher
    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    
    # Using memory storage for Finite State Machine (FSM)
    dp = Dispatcher(storage=MemoryStorage())
    
    # 3. Setup Middlewares
    # RegisterUserMiddleware executes first to register/inject user profile
    dp.message.outer_middleware(RegisterUserMiddleware())
    dp.callback_query.outer_middleware(RegisterUserMiddleware())
    
    # ForceSubscriptionMiddleware executes second, checking channel join state
    dp.message.outer_middleware(ForceSubscriptionMiddleware())
    dp.callback_query.outer_middleware(ForceSubscriptionMiddleware())
    
    # 4. Register Routers (order matters for FSM matching)
    dp.include_router(reaction_router)    # Process reaction callbacks immediately
    dp.include_router(admin_router)       # Process administrative sub-menus
    dp.include_router(scheduling_router)  # Process scheduling wizard
    dp.include_router(user_router)        # Fallback to standard user commands
    
    # 5. Initialize APScheduler
    await init_scheduler(bot)
    
    # 6. Start Polling
    logger.info("Bot is polling. Press Ctrl+C to terminate.")
    try:
        # Delete webhook first to ensure polling starts fresh
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except asyncio.CancelledError:
        logger.info("Polling task cancelled.")
    finally:
        # Graceful shutdown
        logger.info("Shutting down services...")
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped.")
        await bot.session.close()
        logger.info("Bot connection closed.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot application stopped.")
