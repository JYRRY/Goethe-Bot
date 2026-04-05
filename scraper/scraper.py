import asyncio
import logging
import os
import random
from playwright.async_api import async_playwright, Browser, BrowserContext

from data.locations import get_exam_urls, get_main_exam_url, EXAM_URL_SUFFIXES
from scraper.parser import parse_appointments

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MAX_RETRIES = 3
BASE_BACKOFF = 2
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

    async def _fetch_page(self, url: str, label: str) -> str | None:
        """Fetch a single page and return its HTML content."""
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    await self._new_context()

                page = await self._context.new_page()
                try:
                    logger.info(f"Lade: {url} (Versuch {attempt + 1}/{MAX_RETRIES})")
                    response = await page.goto(
                        url, wait_until="domcontentloaded", timeout=60000
                    )

                    if response:
                        logger.info(f"HTTP {response.status}: {url}")
                        if response.status == 403:
                            raise Exception(f"403 Forbidden: {url}")
                        if response.status == 404:
                            logger.debug(f"Seite nicht gefunden (404): {url}")
                            return None

                    # Wait for dynamic content
                    await page.wait_for_timeout(random.randint(3000, 5000))

                    # Accept cookies
                    try:
                        cookie_btn = page.locator(
                            "button:has-text('Alle akzeptieren'), "
                            "button:has-text('Accept all'), "
                            "button:has-text('Akzeptieren'), "
                            ".cookie-consent-accept"
                        )
                        if await cookie_btn.count() > 0:
                            await cookie_btn.first.click()
                            await page.wait_for_timeout(1500)
                    except Exception:
                        pass

                    html_content = await page.content()

                    # Save debug files
                    safe_label = label.replace("/", "_").replace(" ", "_")
                    try:
                        await page.screenshot(
                            path=os.path.join(DEBUG_DIR, f"{safe_label}.png"),
                            full_page=True,
                        )
                        with open(
                            os.path.join(DEBUG_DIR, f"{safe_label}.html"),
                            "w",
                            encoding="utf-8",
                        ) as f:
                            f.write(html_content)
                        logger.info(
                            f"Debug gespeichert: {safe_label} "
                            f"({len(html_content)} Zeichen)"
                        )
                    except Exception as e:
                        logger.debug(f"Debug-Speichern fehlgeschlagen: {e}")

                    title = await page.title()
                    logger.info(f"Titel: {title}")

                    return html_content

                finally:
                    await page.close()

            except Exception as e:
                backoff = BASE_BACKOFF * (2**attempt) + random.uniform(0, 1)
                logger.warning(
                    f"Fehler für {url} (Versuch {attempt + 1}): {e}"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Alle Versuche für {url} fehlgeschlagen.")

        return None

    async def scrape_city(
        self, country_code: str, city: str
    ) -> list[dict]:
        """
        Scrape exam appointments for a specific city.
        Strategy:
        1. Load the main exam page and registration page
        2. Load individual exam type subpages
        3. Collect all found appointments
        """
        exam_urls = get_exam_urls(country_code, city)
        if not exam_urls:
            logger.warning(f"Keine URLs für {city} ({country_code})")
            return []

        all_appointments = []
        seen_urls = set()

        for url_info in exam_urls:
            url = url_info["url"]
            if url in seen_urls:
                continue
            seen_urls.add(url)

            exam_type_filter = url_info["exam_type"]
            page_type = url_info["page_type"]
            label = f"{country_code}_{city}_{page_type}_{exam_type_filter}"

            html = await self._fetch_page(url, label)
            if not html:
                continue

            appointments = parse_appointments(
                html, country_code, city, exam_type_filter
            )
            all_appointments.extend(appointments)

            # Small delay between pages to be respectful
            await asyncio.sleep(random.uniform(1, 3))

        # Deduplicate across all pages
        seen = set()
        unique = []
        for appt in all_appointments:
            key = (
                appt["country_code"],
                appt["city"],
                appt["exam_type"],
                appt["exam_date"],
                appt["exam_time"],
            )
            if key not in seen:
                seen.add(key)
                unique.append(appt)

        logger.info(
            f"Scrape-Ergebnis für {city} ({country_code}): "
            f"{len(unique)} eindeutige Termine"
        )
        return unique


# Global scraper instance
scraper_manager = GoetheScraperManager()
