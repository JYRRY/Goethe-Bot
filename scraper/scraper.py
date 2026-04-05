import asyncio
import json
import logging
import os
import random
import re
from playwright.async_api import async_playwright, Browser, BrowserContext

from data.locations import get_exam_urls, LOCATIONS

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MAX_RETRIES = 2
DEBUG_DIR = "debug"

# Common cookie consent button selectors (Cookiebot, OneTrust, generic)
COOKIE_ACCEPT_SELECTORS = [
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    ".cookie-consent__accept-all",
    "#onetrust-accept-btn-handler",
    "button[data-cookie-accept]",
    ".cc-btn.cc-allow",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Akzeptieren')",
    "button:has-text('Accept all')",
    "a:has-text('Alle akzeptieren')",
]


class GoetheScraperManager:
    """Scrapes Goethe-Institut exam data from rendered pages."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._cookies_accepted = False

    async def start(self):
        os.makedirs(DEBUG_DIR, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        await self._new_context()
        logger.info("Scraper-Browser gestartet.")

    async def _new_context(self):
        if self._context:
            await self._context.close()
        self._context = await self._browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            java_script_enabled=True,
        )
        # Hide webdriver flag to avoid bot detection
        await self._context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        """)
        self._cookies_accepted = False

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Scraper-Browser gestoppt.")

    async def _accept_cookies(self, page) -> bool:
        """Try to find and click the cookie consent accept button."""
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                btn = page.locator(selector).first
                if await btn.is_visible(timeout=1000):
                    await btn.click()
                    logger.info(f"Cookie-Zustimmung geklickt: {selector}")
                    await page.wait_for_timeout(1000)
                    return True
            except Exception:
                continue
        return False

    async def _warm_up_session(self, country_code: str) -> bool:
        """
        Visit the main Goethe page first to establish cookies/session,
        then accept the cookie consent banner.
        """
        if self._cookies_accepted:
            return True

        page = await self._context.new_page()
        try:
            # Visit the main institute page to get session cookies
            country = LOCATIONS.get(country_code, {})
            cities = country.get("cities", {})
            first_city = next(iter(cities.values()), None)
            if first_city:
                main_url = first_city["base_url"].rsplit("/prf", 1)[0] + ".html"
            else:
                main_url = f"https://www.goethe.de/ins/{country_code}/de/index.html"

            logger.info(f"Session aufwärmen: {main_url}")
            resp = await page.goto(main_url, wait_until="domcontentloaded", timeout=30000)

            if resp and resp.status >= 400:
                logger.warning(f"Warm-up Seite Status: {resp.status}")
                # Try the generic Goethe page
                await page.goto("https://www.goethe.de/de/index.html",
                                wait_until="domcontentloaded", timeout=30000)

            # Wait for cookie banner to appear
            await page.wait_for_timeout(3000)

            # Try to accept cookies
            accepted = await self._accept_cookies(page)
            if accepted:
                self._cookies_accepted = True
                logger.info("Cookies akzeptiert.")
            else:
                logger.info("Kein Cookie-Banner gefunden (evtl. nicht nötig).")
                self._cookies_accepted = True  # Continue anyway

            # Save debug screenshot
            try:
                await page.screenshot(path=os.path.join(DEBUG_DIR, "warmup.png"))
            except Exception:
                pass

            return True
        except Exception as e:
            logger.warning(f"Session-Warmup fehlgeschlagen: {e}")
            return False
        finally:
            await page.close()

    async def _scrape_exam_page(self, page_url: str, exam_type: str) -> list[dict]:
        """
        Load a .cfm exam page, wait for JavaScript to render exam data,
        then extract appointments from the rendered DOM.
        """
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    await self._new_context()
                    self._cookies_accepted = False

                page = await self._context.new_page()

                try:
                    logger.info(f"Lade Prüfungsseite: {page_url}")
                    resp = await page.goto(page_url, wait_until="domcontentloaded",
                                           timeout=30000)

                    if resp and resp.status == 404:
                        logger.info(f"Seite nicht gefunden (404): {page_url}")
                        return []
                    if resp and resp.status == 403:
                        logger.warning(f"Zugriff verweigert (403): {page_url}")
                        if attempt < MAX_RETRIES - 1:
                            raise Exception("403 — Neuer Versuch nötig")
                        return []

                    # Accept cookies if banner appears on this page too
                    await page.wait_for_timeout(2000)
                    await self._accept_cookies(page)

                    # Wait for the examfinder widget to render
                    # The widget replaces Handlebars templates like {{eventTimeSpan}}
                    # with actual content after the API call completes.
                    try:
                        await page.wait_for_selector(
                            ".examfinder-result, .examfinder-exam, "
                            ".pr-termin, .event-list-item, "
                            "[class*='examfinder'] table, "
                            "[class*='examfinder'] .row",
                            timeout=15000,
                        )
                        logger.info(f"Examfinder-Widget geladen für {exam_type}")
                    except Exception:
                        logger.info(f"Kein Examfinder-Widget gefunden, prüfe Seiteninhalt...")

                    # Additional wait for any late-loading content
                    await page.wait_for_timeout(3000)

                    # Save debug screenshot and HTML
                    try:
                        safe = exam_type.replace(" ", "_")
                        await page.screenshot(
                            path=os.path.join(DEBUG_DIR, f"page_{safe}.png"),
                            full_page=True,
                        )
                        html = await page.content()
                        with open(os.path.join(DEBUG_DIR, f"page_{safe}.html"), "w") as f:
                            f.write(html[:200000])
                    except Exception:
                        pass

                    # Extract appointments from the rendered page
                    html = await page.content()
                    appointments = self._extract_from_rendered_html(html, exam_type)

                    # Also try extracting from the examfinder widget via JavaScript
                    if not appointments:
                        js_data = await self._extract_via_js(page, exam_type)
                        appointments.extend(js_data)

                    return appointments

                finally:
                    await page.close()

            except Exception as e:
                logger.warning(f"Fehler für {page_url} (Versuch {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))

        return []

    def _extract_from_rendered_html(self, html: str, exam_type: str) -> list[dict]:
        """
        Extract appointment data from the fully rendered HTML.
        After JavaScript executes, the Handlebars templates are replaced
        with actual data in the DOM.
        """
        appointments = []

        # Look for booking/registration links
        booking_pattern = re.compile(
            r'href="(https?://(?:anmeldung\.goethe\.de|www\.goethe\.de)[^"]*(?:anm|book|regist)[^"]*)"',
            re.IGNORECASE,
        )

        # Look for price patterns
        price_pattern = re.compile(
            r'(\d{2,4}(?:[.,]\d{2})?\s*(?:EUR|€|EGP|SAR|MAD|LBP|DZD))',
            re.IGNORECASE,
        )

        # Find the examfinder section of the page
        examfinder_section = re.search(
            r'class="[^"]*examfinder[^"]*"(.*?)(?=class="[^"]*(?:footer|nav|header)',
            html, re.DOTALL | re.IGNORECASE,
        )

        search_html = examfinder_section.group(1) if examfinder_section else html

        # Look for table rows or list items with dates
        row_pattern = re.compile(
            r'<(?:tr|li|div)[^>]*class="[^"]*(?:row|item|result|termin)[^"]*"[^>]*>'
            r'(.*?)</(?:tr|li|div)>',
            re.DOTALL | re.IGNORECASE,
        )

        rows = row_pattern.findall(search_html)
        for row in rows:
            dates = re.findall(r'(\d{1,2}\.\d{1,2}\.\d{4})', row)
            bookings = booking_pattern.findall(row)
            prices = price_pattern.findall(row)

            valid_dates = [d for d in dates if self._is_recent_date(d)]

            if valid_dates:
                appt = {
                    "exam_type": exam_type,
                    "exam_date": valid_dates[0],
                    "exam_time": "",
                    "slots_available": "Verfügbar",
                    "booking_url": bookings[0] if bookings else "",
                    "location": "",
                }
                if prices:
                    appt["slots_available"] += f" ({prices[0]})"
                appointments.append(appt)

        # If no structured rows found, try finding dates in the examfinder area
        if not appointments:
            all_dates = re.findall(r'(\d{1,2}\.\d{1,2}\.\d{4})', search_html)
            all_bookings = booking_pattern.findall(search_html)
            all_prices = price_pattern.findall(search_html)

            valid_dates = [d for d in all_dates if self._is_recent_date(d)]

            for i, date in enumerate(valid_dates):
                appt = {
                    "exam_type": exam_type,
                    "exam_date": date,
                    "exam_time": "",
                    "slots_available": "Verfügbar",
                    "booking_url": all_bookings[i] if i < len(all_bookings) else "",
                    "location": "",
                }
                if i < len(all_prices):
                    appt["slots_available"] += f" ({all_prices[i]})"
                appointments.append(appt)

        # Check for "no exams available" messages
        no_results_patterns = [
            r"vorübergehend nicht angezeigt",
            r"keine.*Termine",
            r"no.*exam.*available",
            r"derzeit.*keine",
            r"aktuell.*keine.*Prüfung",
        ]
        for pattern in no_results_patterns:
            if re.search(pattern, search_html, re.IGNORECASE):
                logger.info(f"Keine Termine verfügbar für {exam_type}")
                return []

        if appointments:
            logger.info(f"DOM: {len(appointments)} Termine für {exam_type} extrahiert")
        else:
            logger.info(f"DOM: Keine Termine für {exam_type} im gerenderten HTML")

        return appointments

    async def _extract_via_js(self, page, exam_type: str) -> list[dict]:
        """
        Try to extract exam data by querying the rendered DOM via JavaScript.
        This catches data that regex might miss.
        """
        appointments = []
        try:
            data = await page.evaluate("""
                () => {
                    const results = [];

                    // Look for examfinder rendered elements
                    const selectors = [
                        '.examfinder-result',
                        '.examfinder-exam',
                        '[class*="examfinder"] .row',
                        '[class*="examfinder"] tr',
                        '.event-list-item',
                        '.pr-termin',
                        '.content-box table tr',
                        '.mod_examfinder .row',
                    ];

                    for (const sel of selectors) {
                        const elements = document.querySelectorAll(sel);
                        for (const el of elements) {
                            const text = el.textContent || '';
                            const links = el.querySelectorAll('a[href]');
                            const bookingLink = Array.from(links)
                                .map(a => a.href)
                                .find(h => h.includes('anmeldung') || h.includes('book') ||
                                           h.includes('anm') || h.includes('regist')) || '';

                            const dateMatch = text.match(/(\\d{1,2}\\.\\d{1,2}\\.\\d{4})/);
                            const priceMatch = text.match(/(\\d{2,4}[.,]?\\d{0,2}\\s*(?:EUR|€|EGP|SAR|MAD|LBP|DZD))/i);

                            if (dateMatch) {
                                results.push({
                                    date: dateMatch[1],
                                    price: priceMatch ? priceMatch[1] : '',
                                    text: text.trim().substring(0, 300),
                                    bookingUrl: bookingLink,
                                });
                            }
                        }
                    }

                    // Check for "no results" messages
                    const bodyText = document.body.textContent || '';
                    if (bodyText.includes('vorübergehend nicht angezeigt') ||
                        bodyText.includes('keine Termine') ||
                        bodyText.includes('derzeit keine')) {
                        results.push({noResults: true});
                    }

                    return results;
                }
            """)

            for item in data:
                if item.get("noResults"):
                    logger.info(f"JS: Keine Termine für {exam_type}")
                    return []

                date_str = item.get("date", "")
                if date_str and self._is_recent_date(date_str):
                    appt = {
                        "exam_type": exam_type,
                        "exam_date": date_str,
                        "exam_time": "",
                        "slots_available": "Verfügbar",
                        "booking_url": item.get("bookingUrl", ""),
                        "location": "",
                    }
                    if item.get("price"):
                        appt["slots_available"] += f" ({item['price']})"
                    appointments.append(appt)

            if appointments:
                logger.info(f"JS: {len(appointments)} Termine für {exam_type}")

        except Exception as e:
            logger.warning(f"JS-Extraktion fehlgeschlagen: {e}")

        return appointments

    @staticmethod
    def _is_recent_date(date_str: str) -> bool:
        """Check if a date string (DD.MM.YYYY) is not too old."""
        try:
            parts = date_str.split(".")
            if len(parts) != 3:
                return False
            year = int(parts[2])
            return year >= 2025
        except (ValueError, IndexError):
            return False

    async def scrape_city(self, country_code: str, city: str) -> list[dict]:
        """Scrape all exam appointments for a city."""
        exam_urls = get_exam_urls(country_code, city)
        if not exam_urls:
            return []

        # Warm up session (get cookies, accept consent) before scraping
        await self._warm_up_session(country_code)

        all_appointments = []

        for url_info in exam_urls:
            url = url_info["url"]
            exam_type = url_info["exam_type"]
            page_type = url_info["page_type"]

            if page_type != "exam_detail":
                continue

            raw_appointments = await self._scrape_exam_page(url, exam_type)

            for appt in raw_appointments:
                appt["country_code"] = country_code
                appt["city"] = city
                all_appointments.append(appt)

            # Delay between pages to avoid rate limiting
            await asyncio.sleep(random.uniform(1.5, 3.0))

        # Deduplicate
        seen = set()
        unique = []
        for appt in all_appointments:
            key = (appt["country_code"], appt["city"], appt["exam_type"],
                   appt["exam_date"])
            if key not in seen:
                seen.add(key)
                unique.append(appt)

        logger.info(f"Ergebnis {city} ({country_code}): {len(unique)} Termine")
        return unique


scraper_manager = GoetheScraperManager()
