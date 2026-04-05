import asyncio
import logging
import os
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
DEBUG_DIR = "data/debug"


class GoetheScraperManager:
    """Manages a persistent browser instance for scraping Goethe-Institut pages."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self):
        """Start the browser."""
        os.makedirs(DEBUG_DIR, exist_ok=True)
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
            java_script_enabled=True,
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
        Returns list of appointment dicts.
        """
        url = get_exam_url(country_code)
        all_appointments = []

        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    await self._new_context()

                page = await self._context.new_page()
                try:
                    logger.info(
                        f"Seite laden: {url} (Versuch {attempt + 1}/{MAX_RETRIES})"
                    )

                    response = await page.goto(url, wait_until="domcontentloaded", timeout=60000)

                    # Log response status
                    if response:
                        logger.info(f"HTTP Status: {response.status} für {url}")
                        if response.status == 403:
                            logger.warning(f"Zugriff verweigert (403) für {url}")
                            raise Exception(f"403 Forbidden für {url}")

                    # Wait for page to fully render
                    await page.wait_for_timeout(5000)

                    # Try to accept cookies if dialog appears
                    try:
                        cookie_btn = page.locator(
                            "button:has-text('Alle akzeptieren'), "
                            "button:has-text('Accept all'), "
                            "button:has-text('Akzeptieren'), "
                            "button:has-text('Alle Cookies akzeptieren'), "
                            "[data-testid='cookie-accept'], "
                            ".cookie-consent-accept, "
                            "#cookie-accept"
                        )
                        if await cookie_btn.count() > 0:
                            await cookie_btn.first.click()
                            logger.info("Cookie-Banner akzeptiert.")
                            await page.wait_for_timeout(2000)
                    except Exception:
                        pass

                    # Wait more for dynamic content
                    await page.wait_for_timeout(3000)

                    # Save debug screenshot and HTML
                    try:
                        screenshot_path = os.path.join(
                            DEBUG_DIR, f"{country_code}_page.png"
                        )
                        await page.screenshot(path=screenshot_path, full_page=True)
                        logger.info(f"Screenshot gespeichert: {screenshot_path}")
                    except Exception as e:
                        logger.warning(f"Screenshot fehlgeschlagen: {e}")

                    # Get page content
                    html_content = await page.content()

                    # Save debug HTML
                    try:
                        html_path = os.path.join(
                            DEBUG_DIR, f"{country_code}_page.html"
                        )
                        with open(html_path, "w", encoding="utf-8") as f:
                            f.write(html_content)
                        logger.info(
                            f"HTML gespeichert: {html_path} "
                            f"({len(html_content)} Zeichen)"
                        )
                    except Exception as e:
                        logger.warning(f"HTML speichern fehlgeschlagen: {e}")

                    # Get the page title for debugging
                    title = await page.title()
                    logger.info(f"Seitentitel: {title}")

                    # Parse appointments
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
