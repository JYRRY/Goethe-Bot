import asyncio
import json
import logging
import os
import random
import re
from playwright.async_api import async_playwright, Browser, BrowserContext, Response

from data.locations import get_exam_urls, EXAM_URL_SUFFIXES

logger = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

MAX_RETRIES = 2
DEBUG_DIR = "debug"

# Regex to extract the examfinder API config from page JavaScript
EXAMFINDER_CONFIG_RE = re.compile(
    r'var\s+examfinderDataCF_\d+\s*=\s*(\{.*?\});', re.DOTALL
)


class GoetheScraperManager:
    """Scrapes Goethe-Institut exam data via their REST API."""

    def __init__(self):
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self):
        os.makedirs(DEBUG_DIR, exist_ok=True)
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-gpu"],
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
        )

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Scraper-Browser gestoppt.")

    async def _extract_api_data(self, page_url: str, exam_type: str) -> list[dict]:
        """
        Load a .cfm exam page, extract the examfinder API config,
        then call the API directly to get exam dates as JSON.
        """
        for attempt in range(MAX_RETRIES):
            try:
                if attempt > 0:
                    await self._new_context()

                page = await self._context.new_page()
                api_responses = []

                # Intercept API responses
                async def handle_response(response: Response):
                    if "/rest/examfinder/" in response.url:
                        try:
                            body = await response.text()
                            api_responses.append({
                                "url": response.url,
                                "status": response.status,
                                "body": body,
                            })
                            logger.info(f"API abgefangen: {response.url} ({response.status})")
                        except Exception:
                            pass

                page.on("response", handle_response)

                try:
                    logger.info(f"Lade: {page_url}")
                    resp = await page.goto(page_url, wait_until="domcontentloaded", timeout=30000)

                    if resp and resp.status == 404:
                        return []
                    if resp and resp.status == 403:
                        raise Exception(f"403 Forbidden: {page_url}")

                    # Wait for API calls to complete
                    await page.wait_for_timeout(8000)

                    # Also extract API config from page source
                    html = await page.content()
                    config = self._parse_examfinder_config(html)

                    if config and not api_responses:
                        # API wasn't called automatically, call it manually
                        api_path = config.get("apiPath", "")
                        if api_path:
                            api_url = f"https://www.goethe.de{api_path}"
                            logger.info(f"API manuell aufrufen: {api_url}")
                            try:
                                api_resp = await page.evaluate(f"""
                                    async () => {{
                                        const resp = await fetch('{api_url}');
                                        return await resp.text();
                                    }}
                                """)
                                api_responses.append({
                                    "url": api_url,
                                    "status": 200,
                                    "body": api_resp,
                                })
                            except Exception as e:
                                logger.warning(f"Manueller API-Aufruf fehlgeschlagen: {e}")

                    # Parse API responses
                    appointments = []
                    for api_resp in api_responses:
                        parsed = self._parse_api_response(api_resp["body"], exam_type)
                        appointments.extend(parsed)
                        # Save debug
                        try:
                            safe = exam_type.replace(" ", "_")
                            with open(os.path.join(DEBUG_DIR, f"api_{safe}.json"), "w") as f:
                                f.write(api_resp["body"][:50000])
                        except Exception:
                            pass

                    if not appointments and config:
                        logger.info(f"Keine API-Daten. Config: {json.dumps(config, indent=2)[:500]}")

                    return appointments

                finally:
                    await page.close()

            except Exception as e:
                logger.warning(f"Fehler für {page_url} (Versuch {attempt + 1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 * (attempt + 1))

        return []

    def _parse_examfinder_config(self, html: str) -> dict | None:
        """Extract the examfinderDataCF config from page JavaScript."""
        match = EXAMFINDER_CONFIG_RE.search(html)
        if not match:
            return None
        try:
            # The config is JavaScript object notation, mostly valid JSON
            config_str = match.group(1)
            # Fix JavaScript-style issues
            config_str = re.sub(r'(\w+):', r'"\1":', config_str)
            config_str = config_str.replace("'", '"')
            config = json.loads(config_str)
            logger.info(f"ExamFinder Config: apiPath={config.get('apiPath', 'N/A')}")
            return config
        except json.JSONDecodeError:
            # Try extracting just the apiPath
            api_match = re.search(r'"apiPath"\s*:\s*"([^"]+)"', match.group(1))
            if api_match:
                return {"apiPath": api_match.group(1)}
            return None

    def _parse_api_response(self, body: str, exam_type_filter: str) -> list[dict]:
        """Parse the examfinder API JSON response into appointments."""
        appointments = []
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            logger.warning(f"API-Antwort ist kein gültiges JSON: {body[:200]}")
            return []

        # The API returns exam data - structure may vary
        # Common patterns: {"DATA": [...]} or direct array
        exams = []
        if isinstance(data, list):
            exams = data
        elif isinstance(data, dict):
            exams = data.get("DATA", data.get("data", data.get("exams", [])))
            if isinstance(exams, dict):
                exams = [exams]

        logger.info(f"API: {len(exams)} Prüfungen gefunden")

        for exam in exams:
            if not isinstance(exam, dict):
                continue

            # Extract fields (field names may vary)
            date = (exam.get("eventTimeSpan") or exam.get("startDate") or
                    exam.get("date") or exam.get("examDate") or "")
            price = (exam.get("price") or exam.get("priceExternal") or
                     exam.get("fee") or "")
            location = (exam.get("locationName") or exam.get("location") or
                        exam.get("city") or "")
            status = (exam.get("status") or exam.get("availability") or "")
            booking_url = (exam.get("bookingUrl") or exam.get("bookingLink") or
                           exam.get("registrationUrl") or "")
            exam_name = (exam.get("examName") or exam.get("name") or
                         exam.get("DESCRIPTION") or "")
            seats = exam.get("freeSeats", exam.get("availableSeats", ""))

            # Determine availability
            if status.lower() in ("bookable", "available", "open"):
                slots = "Verfügbar"
            elif status.lower() in ("full", "sold_out", "closed"):
                slots = "Ausgebucht"
            elif seats:
                slots = f"{seats} Plätze frei" if str(seats) != "0" else "Ausgebucht"
            else:
                slots = "Verfügbar" if booking_url else "Unbekannt"

            if price:
                slots += f" ({price})"

            appointment = {
                "exam_type": exam_type_filter,
                "exam_date": str(date) if date else "Siehe Website",
                "exam_time": "",
                "slots_available": slots,
                "booking_url": str(booking_url),
                "location": location,
            }
            appointments.append(appointment)

            logger.info(
                f"  Termin: {exam_type_filter} | {date} | {slots} | "
                f"{location} | {booking_url[:50] if booking_url else 'kein Link'}"
            )

        return appointments

    async def scrape_city(self, country_code: str, city: str) -> list[dict]:
        """Scrape all exam appointments for a city using the API."""
        exam_urls = get_exam_urls(country_code, city)
        if not exam_urls:
            return []

        all_appointments = []

        for url_info in exam_urls:
            url = url_info["url"]
            exam_type = url_info["exam_type"]
            page_type = url_info["page_type"]

            # Only scrape .cfm exam detail pages (they have the API)
            if page_type != "exam_detail":
                continue

            raw_appointments = await self._extract_api_data(url, exam_type)

            for appt in raw_appointments:
                appt["country_code"] = country_code
                appt["city"] = city
                all_appointments.append(appt)

            # Small delay between pages
            await asyncio.sleep(random.uniform(1, 2))

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
