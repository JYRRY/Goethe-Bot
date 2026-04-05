"""
Goethe-Institut exam scraper using Playwright with stealth.

Strategy:
1. Use Firefox (harder to fingerprint than Chromium) with stealth patches
2. Accept cookie consent banner first
3. Navigate to each exam .cfm page
4. Wait for JavaScript to render exam data into the DOM
5. Extract dates, location, exam parts, prices, booking links from rendered HTML
6. Filter out fully booked entries and past dates
7. Filter by location (e.g. Dokki vs Hurghada on same page)
"""

import asyncio
import logging
import os
import random
import re

from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from playwright_stealth import stealth_async

from data.locations import get_exam_urls, LOCATIONS

logger = logging.getLogger(__name__)

DEBUG_DIR = "/app/debug"

# Cookie consent button selectors — tried in order
COOKIE_ACCEPT_SELECTORS = [
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "#onetrust-accept-btn-handler",
    "button:has-text('Alle akzeptieren')",
    "button:has-text('Alle Cookies akzeptieren')",
    "button:has-text('Akzeptieren')",
    "a:has-text('Alle akzeptieren')",
    "button:has-text('Accept all')",
    "button:has-text('Accept')",
    ".cookie-consent__accept-all",
    ".cc-btn.cc-allow",
    "button[data-cookie-accept]",
]


class GoetheScraperManager:
    """Scrapes Goethe-Institut exam pages for appointment data."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._browser_type = "firefox"
        self._session_ready = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        os.makedirs(DEBUG_DIR, exist_ok=True)
        self._playwright = await async_playwright().start()

        try:
            self._browser = await self._playwright.firefox.launch(
                headless=True, args=[],
            )
            self._browser_type = "firefox"
            logger.info("Scraper gestartet mit Firefox.")
        except Exception as e:
            logger.warning(f"Firefox nicht verfügbar ({e}), nutze Chromium.")
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox", "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage", "--disable-gpu",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            self._browser_type = "chromium"
            logger.info("Scraper gestartet mit Chromium.")

        await self._create_context()

    async def _create_context(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass

        self._context = await self._browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="de-DE",
            timezone_id="Europe/Berlin",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) "
                "Gecko/20100101 Firefox/132.0"
                if self._browser_type == "firefox" else
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            java_script_enabled=True,
        )
        self._session_ready = False

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Scraper gestoppt.")

    # ------------------------------------------------------------------
    # Cookie / session helpers
    # ------------------------------------------------------------------

    async def _apply_stealth(self, page: Page):
        try:
            await stealth_async(page)
        except Exception as e:
            logger.debug(f"Stealth-Patch fehlgeschlagen: {e}")

    async def _try_accept_cookies(self, page: Page) -> bool:
        for selector in COOKIE_ACCEPT_SELECTORS:
            try:
                loc = page.locator(selector).first
                if await loc.is_visible(timeout=800):
                    await loc.click()
                    logger.info(f"Cookie-Banner akzeptiert: {selector}")
                    await page.wait_for_timeout(1500)
                    return True
            except Exception:
                continue
        return False

    async def _ensure_session(self, country_code: str):
        if self._session_ready:
            return

        page = await self._context.new_page()
        await self._apply_stealth(page)

        try:
            country = LOCATIONS.get(country_code, {})
            cities = country.get("cities", {})
            first_city = next(iter(cities.values()), None)

            if first_city:
                warmup_url = first_city["base_url"].rsplit("/prf", 1)[0] + ".html"
            else:
                warmup_url = f"https://www.goethe.de/ins/{country_code}/de/index.html"

            logger.info(f"Session aufwärmen: {warmup_url}")
            resp = await page.goto(warmup_url, wait_until="networkidle", timeout=45000)

            if resp and resp.status >= 400:
                logger.warning(f"Warmup-Status {resp.status}, versuche Hauptseite...")
                await page.goto(
                    "https://www.goethe.de/de/index.html",
                    wait_until="networkidle", timeout=30000,
                )

            await page.wait_for_timeout(2000)
            await self._try_accept_cookies(page)

            try:
                await page.screenshot(path=os.path.join(DEBUG_DIR, "warmup.png"))
            except Exception:
                pass

            self._session_ready = True
            logger.info("Session bereit.")

        except Exception as e:
            logger.warning(f"Session-Warmup Fehler: {e}")
            self._session_ready = True
        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Page scraping
    # ------------------------------------------------------------------

    async def _scrape_single_page(self, url: str, exam_type: str) -> list[dict]:
        page = await self._context.new_page()
        await self._apply_stealth(page)

        try:
            logger.info(f"Lade Seite: {url} ({exam_type})")
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=40000)

            page_status = resp.status if resp else 0
            logger.info(f"Seiten-Status: {page_status} für {exam_type}")

            if page_status in (404, 403):
                logger.warning(f"Seite {page_status}: {url}")
                return []

            await page.wait_for_timeout(2000)
            await self._try_accept_cookies(page)

            # Wait for examfinder widget to render
            exam_selectors = [
                "[class*='examfinder'] table",
                "[class*='examfinder'] .row",
                ".examfinder-result",
                ".event-list-item",
                ".termin-row",
                ".pr-termin",
            ]

            for sel in exam_selectors:
                try:
                    await page.wait_for_selector(sel, timeout=5000)
                    logger.info(f"Widget gerendert ({sel}) für {exam_type}")
                    break
                except Exception:
                    continue
            else:
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except Exception:
                    pass
                await page.wait_for_timeout(5000)

            # Save debug info
            safe_name = exam_type.replace(" ", "_")
            try:
                await page.screenshot(
                    path=os.path.join(DEBUG_DIR, f"page_{safe_name}.png"),
                    full_page=True,
                )
            except Exception:
                pass

            html_content = await page.content()
            try:
                with open(os.path.join(DEBUG_DIR, f"page_{safe_name}.html"), "w") as f:
                    f.write(html_content[:300000])
            except Exception:
                pass

            # Extract data
            appointments = await self._js_extract(page, exam_type)

            if not appointments:
                appointments = self._regex_extract(html_content, exam_type)

            if not appointments:
                no_data = await self._check_no_results(page)
                if no_data:
                    logger.info(f"Seite meldet: keine Termine für {exam_type}")
                else:
                    logger.info(f"Keine Termine gefunden für {exam_type}")
                    try:
                        visible_text = await page.evaluate(
                            "() => document.body.innerText.substring(0, 1000)"
                        )
                        logger.debug(f"Seitentext: {visible_text[:500]}")
                    except Exception:
                        pass

            return appointments

        except Exception as e:
            logger.error(f"Fehler beim Laden von {url}: {e}")
            return []
        finally:
            await page.close()

    async def _js_extract(self, page: Page, exam_type: str) -> list[dict]:
        """Extract exam data from DOM via JavaScript."""
        try:
            raw = await page.evaluate("""
                () => {
                    const results = [];
                    const dateRegex = /(\\d{1,2}\\.\\d{1,2}\\.\\d{4})/;
                    const priceRegex = /(\\d{2,4}[.,]?\\d{0,2}\\s*(?:EUR|€|EGP|SAR|MAD|LBP|DZD|USD))/i;

                    // Today for filtering
                    const now = new Date();
                    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

                    function isDateInFuture(dateStr) {
                        const [dd, mm, yyyy] = dateStr.split('.').map(Number);
                        return new Date(yyyy, mm - 1, dd) >= today;
                    }

                    // Known location names to extract from text
                    const locationKeywords = ['dokki', 'hurghada', 'alexandria',
                        'casablanca', 'rabat', 'algier', 'riad', 'dschidda',
                        'jeddah', 'beirut', 'kairo', 'cairo'];

                    // Exam part keywords
                    const partKeywords = {
                        'schriftlich': 'Schriftlich',
                        'mündlich': 'Mündlich',
                        'mundlich': 'Mündlich',
                        'lesen': 'Lesen',
                        'hören': 'Hören',
                        'horen': 'Hören',
                        'schreiben': 'Schreiben',
                        'sprechen': 'Sprechen',
                    };

                    // Fully booked keywords — skip these
                    const bookedKeywords = ['ausgebucht', 'fully booked',
                        'belegt', 'warteliste', 'sold out'];

                    function extractLocation(text) {
                        const lower = text.toLowerCase();
                        for (const kw of locationKeywords) {
                            if (lower.includes(kw)) {
                                return kw.charAt(0).toUpperCase() + kw.slice(1);
                            }
                        }
                        return '';
                    }

                    function extractParts(text) {
                        const lower = text.toLowerCase();
                        const found = [];
                        for (const [kw, label] of Object.entries(partKeywords)) {
                            if (lower.includes(kw)) {
                                // If we find Schriftlich, don't also add Lesen/Hören/Schreiben
                                if (['lesen', 'hören', 'horen', 'schreiben'].includes(kw) &&
                                    lower.includes('schriftlich')) continue;
                                // If we find Mündlich, don't also add Sprechen
                                if (kw === 'sprechen' && (lower.includes('mündlich') ||
                                    lower.includes('mundlich'))) continue;
                                if (!found.includes(label)) found.push(label);
                            }
                        }
                        return found.join(', ');
                    }

                    function isFullyBooked(text) {
                        const lower = text.toLowerCase();
                        return bookedKeywords.some(kw => lower.includes(kw));
                    }

                    const rowSelectors = [
                        '[class*="examfinder"] tr',
                        '[class*="examfinder"] .row',
                        '[class*="examfinder"] li',
                        '.examfinder-result',
                        '.event-list-item',
                        '.termin-row',
                        '.pr-termin',
                        '.content-box table tr',
                        '.content-box .row',
                        'table.table tr',
                        '.mod_examfinder tr',
                        '.mod_examfinder .row',
                        '.pruefungstermine tr',
                        '.pruefungstermine .row',
                    ];

                    const seen = new Set();

                    for (const sel of rowSelectors) {
                        const els = document.querySelectorAll(sel);
                        for (const el of els) {
                            const text = (el.textContent || '').trim();
                            if (text.length < 5) continue;

                            const dateMatch = text.match(dateRegex);
                            if (!dateMatch) continue;

                            const date = dateMatch[1];
                            if (!isDateInFuture(date)) continue;

                            // Skip fully booked entries
                            if (isFullyBooked(text)) continue;

                            const location = extractLocation(text);
                            const examParts = extractParts(text);
                            const priceMatch = text.match(priceRegex);

                            // Deduplicate by (date, location, examParts)
                            const key = date + '|' + location + '|' + examParts;
                            if (seen.has(key)) continue;
                            seen.add(key);

                            // Find booking link
                            let bookingUrl = '';
                            const links = el.querySelectorAll('a[href]');
                            for (const a of links) {
                                const href = a.href || '';
                                if (href.includes('anmeldung') || href.includes('anm') ||
                                    href.includes('book') || href.includes('regist') ||
                                    href.includes('webshop')) {
                                    bookingUrl = href;
                                    break;
                                }
                            }

                            results.push({
                                date: date,
                                location: location,
                                examParts: examParts,
                                price: priceMatch ? priceMatch[1] : '',
                                bookingUrl: bookingUrl,
                                snippet: text.substring(0, 300),
                            });
                        }
                    }

                    // Fallback: scan entire page body
                    if (results.length === 0) {
                        const body = document.body.innerText || '';
                        const allDates = body.match(/(\\d{1,2}\\.\\d{1,2}\\.\\d{4})/g) || [];

                        for (const date of allDates) {
                            if (!isDateInFuture(date)) continue;

                            const key = date + '||';
                            if (seen.has(key)) continue;
                            seen.add(key);

                            // Check if nearby text says fully booked
                            const idx = body.indexOf(date);
                            const nearby = body.substring(
                                Math.max(0, idx - 200), idx + 200
                            ).toLowerCase();
                            if (bookedKeywords.some(kw => nearby.includes(kw))) continue;

                            let bookingUrl = '';
                            const allLinks = document.querySelectorAll('a[href]');
                            for (const a of allLinks) {
                                const href = a.href || '';
                                if (href.includes('anmeldung') || href.includes('webshop')) {
                                    bookingUrl = href;
                                    break;
                                }
                            }

                            const nearbyText = body.substring(
                                Math.max(0, idx - 300), idx + 300
                            );

                            results.push({
                                date: date,
                                location: extractLocation(nearbyText),
                                examParts: extractParts(nearbyText),
                                price: '',
                                bookingUrl: bookingUrl,
                                snippet: '',
                            });
                        }
                    }

                    return results;
                }
            """)

            appointments = []
            for item in raw:
                appt = {
                    "exam_type": exam_type,
                    "exam_date": item["date"],
                    "location": item.get("location", ""),
                    "exam_parts": item.get("examParts", ""),
                    "slots_available": "Verfügbar",
                    "booking_url": item.get("bookingUrl", ""),
                }
                price = item.get("price", "")
                if price:
                    appt["slots_available"] += f" — {price}"

                appointments.append(appt)
                logger.info(
                    f"  Gefunden: {exam_type} | {item['date']} | "
                    f"Ort={item.get('location', '?')} | "
                    f"Teile={item.get('examParts', '?')} | "
                    f"{item.get('snippet', '')[:80]}"
                )

            if appointments:
                logger.info(f"JS-Extraktion: {len(appointments)} Termine für {exam_type}")

            return appointments

        except Exception as e:
            logger.warning(f"JS-Extraktion Fehler: {e}")
            return []

    def _regex_extract(self, html: str, exam_type: str) -> list[dict]:
        """Fallback: extract exam dates from rendered HTML via regex."""
        from datetime import date as date_cls
        appointments = []
        seen_dates = set()

        ef_match = re.search(
            r'class="[^"]*examfinder[^"]*"(.*)',
            html, re.DOTALL | re.IGNORECASE,
        )
        search_area = ef_match.group(1)[:50000] if ef_match else html

        # Clean out non-content areas
        search_area = re.sub(r'<script[^>]*>.*?</script>', '', search_area, flags=re.DOTALL)
        search_area = re.sub(r'<style[^>]*>.*?</style>', '', search_area, flags=re.DOTALL)
        search_area = re.sub(r'<nav[^>]*>.*?</nav>', '', search_area, flags=re.DOTALL)
        search_area = re.sub(r'<footer[^>]*>.*?</footer>', '', search_area, flags=re.DOTALL)

        date_pattern = re.compile(r'(\d{1,2}\.\d{1,2}\.\d{4})')
        booking_pattern = re.compile(
            r'href="(https?://[^"]*(?:anmeldung|anm|webshop|book|regist)[^"]*)"',
            re.IGNORECASE,
        )
        price_pattern = re.compile(
            r'(\d{2,4}[.,]?\d{0,2}\s*(?:EUR|€|EGP|SAR|MAD|LBP|DZD|USD))',
            re.IGNORECASE,
        )
        booked_pattern = re.compile(
            r'ausgebucht|belegt|warteliste|fully booked|sold out',
            re.IGNORECASE,
        )

        today = date_cls.today()
        all_dates = date_pattern.findall(search_area)
        all_bookings = booking_pattern.findall(search_area)
        all_prices = price_pattern.findall(search_area)

        for date_str in all_dates:
            if date_str in seen_dates:
                continue
            try:
                parts = date_str.split(".")
                exam_date = date_cls(int(parts[2]), int(parts[1]), int(parts[0]))
                if exam_date < today:
                    continue
            except (ValueError, IndexError):
                continue

            # Check if nearby text says fully booked
            idx = search_area.find(date_str)
            nearby = search_area[max(0, idx - 200):idx + 200]
            if booked_pattern.search(nearby):
                continue

            seen_dates.add(date_str)
            appt = {
                "exam_type": exam_type,
                "exam_date": date_str,
                "location": "",
                "exam_parts": "",
                "slots_available": "Verfügbar",
                "booking_url": all_bookings[0] if all_bookings else "",
            }
            if all_prices:
                appt["slots_available"] += f" — {all_prices[0]}"

            appointments.append(appt)

        if appointments:
            logger.info(f"Regex-Extraktion: {len(appointments)} Termine für {exam_type}")

        return appointments

    async def _check_no_results(self, page: Page) -> bool:
        try:
            text = await page.evaluate(
                "() => (document.body.innerText || '').toLowerCase()"
            )
            no_result_phrases = [
                "vorübergehend nicht angezeigt",
                "keine termine",
                "derzeit keine",
                "aktuell keine prüfung",
                "no exam",
                "currently no exam",
                "nicht verfügbar",
                "leider keine",
            ]
            return any(phrase in text for phrase in no_result_phrases)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def scrape_city(self, country_code: str, city: str) -> list[dict]:
        """Scrape all exam types for one city. Returns list of appointment dicts."""
        exam_urls = get_exam_urls(country_code, city)
        if not exam_urls:
            logger.warning(f"Keine URLs für {city} ({country_code})")
            return []

        await self._ensure_session(country_code)

        # Get location filter for this city (e.g. "dokki" or "hurghada")
        city_info = LOCATIONS.get(country_code, {}).get("cities", {}).get(city, {})
        location_filter = city_info.get("location_filter", "").lower()

        all_appointments = []

        for url_info in exam_urls:
            if url_info["page_type"] != "exam_detail":
                continue

            url = url_info["url"]
            exam_type = url_info["exam_type"]

            appts = await self._scrape_single_page(url, exam_type)

            for appt in appts:
                # Apply location filter if set
                if location_filter:
                    appt_location = appt.get("location", "").lower()
                    if appt_location and location_filter not in appt_location:
                        logger.debug(
                            f"  Übersprungen (Ort-Filter): {appt['exam_date']} "
                            f"Ort={appt.get('location', '')} != {city}"
                        )
                        continue

                appt["country_code"] = country_code
                appt["city"] = city
                all_appointments.append(appt)

            await asyncio.sleep(random.uniform(2.0, 4.0))

        # Deduplicate
        seen = set()
        unique = []
        for appt in all_appointments:
            key = (appt["country_code"], appt["city"],
                   appt["exam_type"], appt["exam_date"],
                   appt.get("exam_parts", ""))
            if key not in seen:
                seen.add(key)
                unique.append(appt)

        logger.info(f"Ergebnis {city} ({country_code}): {len(unique)} Termine")
        return unique


scraper_manager = GoetheScraperManager()
