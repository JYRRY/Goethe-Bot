import asyncio
import logging
from datetime import date as date_cls
from telegram import Bot
from telegram.error import TelegramError

from bot import messages
from bot.config import SCRAPE_INTERVAL_MINUTES
from data.locations import LOCATIONS
from database.subscriptions import get_active_locations
from database.appointments import (
    upsert_appointment,
    get_due_booking_watches,
    mark_watch_reminded,
)
from notifications.notifier import notify_new_appointment, _escape_md
from scraper.scraper import scraper_manager

logger = logging.getLogger(__name__)

_running = False
_task: asyncio.Task | None = None

MAX_CONCURRENT = 3  # max cities scraped in parallel


async def _scrape_location(bot: Bot, loc: dict, semaphore: asyncio.Semaphore) -> int:
    """Scrape a single location under semaphore. Returns count of new appointments."""
    async with semaphore:
        country_code = loc["country_code"]
        city = loc["city"]
        country_name = LOCATIONS.get(country_code, {}).get("name", country_code)
        new_count = 0

        logger.info(f"Scrape: {city} ({country_name})")

        try:
            appointments = await scraper_manager.scrape_city(country_code, city)

            for appt in appointments:
                is_new, appt_hash = await upsert_appointment(
                    country_code=appt["country_code"],
                    city=appt["city"],
                    exam_type=appt["exam_type"],
                    exam_date=appt["exam_date"],
                    exam_parts=appt.get("exam_parts", ""),
                    slots_available=appt.get("slots_available", ""),
                    booking_url=appt.get("booking_url", ""),
                    booking_opens=appt.get("booking_opens", ""),
                    price=appt.get("price", ""),
                )

                if is_new:
                    new_count += 1
                    await notify_new_appointment(bot, appt, appt_hash)

        except Exception as e:
            logger.error(
                f"Scraping-Fehler für {city} ({country_code}): {e}",
                exc_info=True,
            )

        return new_count


async def scrape_job(bot: Bot):
    """Run a single scrape cycle for all active subscription locations."""
    active_locations = await get_active_locations()

    if not active_locations:
        logger.debug("Keine aktiven Abos — Scraping übersprungen.")
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = [_scrape_location(bot, loc, semaphore) for loc in active_locations]
    results = await asyncio.gather(*tasks)

    total_new = sum(results)
    if total_new > 0:
        logger.info(f"Scrape-Zyklus: {total_new} neue Termine gefunden.")
    else:
        logger.info("Scrape-Zyklus: Keine neuen Termine.")


async def check_booking_reminders(bot: Bot):
    """Send reminders for booking watches whose booking_opens date has arrived."""
    try:
        due_watches = await get_due_booking_watches()
    except Exception as e:
        logger.error(f"Fehler beim Laden der Booking-Watches: {e}")
        return

    for watch in due_watches:
        country_name = LOCATIONS.get(watch["country_code"], {}).get(
            "name", watch["country_code"]
        )

        fmt_kwargs = {
            "exam_date": _escape_md(watch["exam_date"]),
            "city": _escape_md(watch["city"]),
            "country": _escape_md(country_name),
        }

        text = messages.BOOKING_REMINDER.format(**fmt_kwargs)

        try:
            await bot.send_message(
                chat_id=watch["user_id"],
                text=text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
            )
            await mark_watch_reminded(watch["id"])
            logger.info(
                f"Buchungs-Erinnerung gesendet an {watch['user_id']} "
                f"für {watch['exam_date']} in {watch['city']}"
            )
        except TelegramError as e:
            logger.warning(f"Erinnerung an {watch['user_id']} fehlgeschlagen: {e}")


async def _scheduler_loop(bot: Bot):
    """Continuous scraping loop with configurable interval."""
    global _running
    interval = SCRAPE_INTERVAL_MINUTES * 60

    logger.info(f"Scheduler gestartet: Intervall = {SCRAPE_INTERVAL_MINUTES} Min.")

    while _running:
        try:
            await scrape_job(bot)
            await check_booking_reminders(bot)
        except Exception as e:
            logger.error(f"Scheduler-Fehler: {e}", exc_info=True)

        await asyncio.sleep(interval)


def start_scheduler(bot: Bot):
    """Start the background scraping scheduler."""
    global _running, _task
    if _running:
        return
    _running = True
    _task = asyncio.create_task(_scheduler_loop(bot))
    logger.info("Scheduler gestartet.")


async def stop_scheduler():
    """Stop the background scraping scheduler."""
    global _running, _task
    _running = False
    if _task:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
        _task = None
    logger.info("Scheduler gestoppt.")
