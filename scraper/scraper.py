import asyncio
import logging
import random
from playwright.async_api import async_playwright, Browser, BrowserContext

from data.locations import get_exam_url
from scraper.parser import parse_appointments

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MAX_RETRIES = 3
BASE_BACKOFF = 2  # seconds


class GoetheScraperManager:
    """Manages a persistent browser instance for scraping Goethe-Institut pages."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self):
        """Start the browser."""
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        await self._new_context()
        logger.info("Scraper-Browser gestartet.")

    async def _new_context(self):
        """Create a new browser context with random user agent."""
        if self._context:
            await self._context.close()
        ua = random.choice(USER_AGENTS)
        self._context = await self._browser.new_context(
            user_agent=ua,
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
        )

    async def stop(self):
        """Close the browser."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Scraper-Browser gestoppt.")

    async def scrape_country(self, country_code: str, cities: list[str]) -> list[dict]:
        """
        Scrape exam appointments for a specific country.
        Returns list of appointment dicts with keys:
            country_code, city, exam_type, exam_date, exam_time,
            slots_available, booking_url
        """
        url = get_exam_url(country_code)
        all_appointments = []

        for attempt in range(MAX_RETRIES):
            try:
                # Rotate context occasionally
                if attempt > 0:
                    await self._new_context()

                page = await self._context.new_page()
                try:
                    logger.info(
                        f"Seite laden: {url} (Versuch {attempt + 1}/{MAX_RETRIES})"
                    )

                    await page.goto(url, wait_until="networkidle", timeout=60000)

                    # Wait for content to render
                    await page.wait_for_timeout(random.randint(2000, 4000))

                    # Try to accept cookies if dialog appears
                    try:
                        cookie_btn = page.locator(
                            "button:has-text('Alle akzeptieren'), "
                            "button:has-text('Accept all'), "
                            "button:has-text('Akzeptieren'), "
                            "[data-testid='cookie-accept']"
                        )
                        if await cookie_btn.count() > 0:
                            await cookie_btn.first.click()
                            await page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    # Get page content
                    html_content = await page.content()
                    appointments = parse_appointments(
                        html_content, country_code, cities
                    )
                    all_appointments.extend(appointments)

                    logger.info(
                        f"{len(appointments)} Termine gefunden für {country_code}"
                    )
                    break

                finally:
                    await page.close()

            except Exception as e:
                backoff = BASE_BACKOFF * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Scraping-Fehler für {country_code} "
                    f"(Versuch {attempt + 1}/{MAX_RETRIES}): {e}"
                )
                if attempt < MAX_RETRIES - 1:
                    logger.info(f"Warte {backoff:.1f}s vor erneutem Versuch...")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(
                        f"Alle Versuche für {country_code} fehlgeschlagen."
                    )

        return all_appointments


# Global scraper instance
scraper_manager = GoetheScraperManager()
