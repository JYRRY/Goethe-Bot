import asyncio
import logging
import sys

from telegram.ext import Application

from bot.config import BOT_TOKEN, LOG_LEVEL, BOT_NAME
from bot.handlers import register_handlers
from database.models import init_db
from scraper.scraper import scraper_manager
from scraper.scheduler import start_scheduler, stop_scheduler


def setup_logging():
    """Configure logging."""
    logging.basicConfig(
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("playwright").setLevel(logging.WARNING)


async def post_init(application: Application):
    """Called after the application is initialized."""
    # Initialize database
    await init_db()

    # Start the Playwright browser
    await scraper_manager.start()

    # Start the scraping scheduler
    start_scheduler(application.bot)

    logging.getLogger(__name__).info(f"{BOT_NAME} gestartet und bereit!")


async def post_shutdown(application: Application):
    """Called when the application is shutting down."""
    await stop_scheduler()
    await scraper_manager.stop()
    logging.getLogger(__name__).info(f"{BOT_NAME} heruntergefahren.")


def main():
    """Main entry point."""
    setup_logging()
    logger = logging.getLogger(__name__)

    if not BOT_TOKEN:
        logger.error(
            "BOT_TOKEN nicht gesetzt! Bitte .env-Datei erstellen "
            "(siehe .env.example)."
        )
        sys.exit(1)

    logger.info(f"Starte {BOT_NAME}...")

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .post_shutdown(post_shutdown)
        .build()
    )

    register_handlers(application)

    # Run bot with polling
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
