import asyncio
import logging
from telegram import Bot

from bot.config import SCRAPE_INTERVAL_MINUTES
from data.locations import LOCATIONS, get_cities
from database.subscriptions import get_active_locations
from database.appointments import upsert_appointment
from notifications.notifier import notify_new_appointment
from scraper.scraper import scraper_manager

logger = logging.getLogger(__name__)

_running = False
_task: asyncio.Task | None = None


async def scrape_job(bot: Bot):
    """Run a single scrape cycle for all active subscription locations."""
    active_locations = await get_active_locations()

    if not active_locations:
        logger.debug("Keine aktiven Abos — Scraping übersprungen.")
        return

    # Group by country for efficient scraping
    country_cities: dict[str, set[str]] = {}
    for loc in active_locations:
        code = loc["country_code"]
        city = loc["city"]
        if code not in country_cities:
            country_cities[code] = set()
        country_cities[code].add(city)

    total_new = 0

    for country_code, cities in country_cities.items():
        city_list = list(cities)
        logger.info(
            f"Scrape: {LOCATIONS.get(country_code, {}).get('name', country_code)} "
            f"({', '.join(city_list)})"
        )

        try:
            appointments = await scraper_manager.scrape_country(
                country_code, city_list
            )

            for appt in appointments:
                is_new, appt_hash = await upsert_appointment(
                    country_code=appt["country_code"],
                    city=appt["city"],
                    exam_type=appt["exam_type"],
                    exam_date=appt["exam_date"],
                    exam_time=appt.get("exam_time", ""),
                    slots_available=appt.get("slots_available", ""),
                    booking_url=appt.get("booking_url", ""),
                )

                if is_new:
                    total_new += 1
                    await notify_new_appointment(bot, appt, appt_hash)

        except Exception as e:
            logger.error(f"Scraping-Fehler für {country_code}: {e}", exc_info=True)

    if total_new > 0:
        logger.info(f"Scrape-Zyklus abgeschlossen: {total_new} neue Termine gefunden.")
    else:
        logger.debug("Scrape-Zyklus abgeschlossen: Keine neuen Termine.")


async def _scheduler_loop(bot: Bot):
    """Continuous scraping loop with configurable interval."""
    global _running
    interval = SCRAPE_INTERVAL_MINUTES * 60

    logger.info(
        f"Scheduler gestartet: Intervall = {SCRAPE_INTERVAL_MINUTES} Minuten"
    )

    while _running:
        try:
            await scrape_job(bot)
        except Exception as e:
            logger.error(f"Unerwarteter Scheduler-Fehler: {e}", exc_info=True)

        await asyncio.sleep(interval)


def start_scheduler(bot: Bot):
    """Start the background scraping scheduler."""
    global _running, _task
    if _running:
        logger.warning("Scheduler läuft bereits.")
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
