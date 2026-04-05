import logging
import re

logger = logging.getLogger(__name__)

# Exam level patterns
EXAM_PATTERN = re.compile(
    r"\b(?:Goethe-Zertifikat\s+)?(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE
)

# Date patterns
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4})\b"
)

# Time pattern
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2})\s*(?:Uhr)?\b")

# Price pattern (indicates an active exam offering)
PRICE_PATTERN = re.compile(r"(\d+[\.,]?\d*)\s*(?:EUR|€|EGP|MAD|DZD|SAR|USD|LBP)")

AVAILABLE_KEYWORDS = [
    "verfügbar", "available", "freie plätze", "free places",
    "anmelden", "register", "buchen", "book", "plätze frei",
    "zur anmeldung", "jetzt anmelden", "noch plätze",
    "termin", "nächster termin", "prüfungstermin",
]

UNAVAILABLE_KEYWORDS = [
    "ausgebucht", "fully booked", "keine plätze", "no places",
    "warteliste", "waiting list", "sold out", "nicht verfügbar",
    "belegt", "abgesagt", "cancelled", "derzeit keine",
]


def _extract_links(html: str) -> list[tuple[str, str]]:
    """Extract (href, text) pairs from HTML."""
    pattern = re.compile(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    results = []
    for href, text in pattern.findall(html):
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        if not href.startswith("http") and href.startswith("/"):
            href = f"https://www.goethe.de{href}"
        results.append((href, clean_text))
    return results


def _clean_html_to_text(html: str) -> str:
    """Strip HTML tags and clean up text."""
    text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "\n", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"&[a-z]+;", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def parse_appointments(
    html_content: str,
    country_code: str,
    city: str,
    exam_type_filter: str = "ALL",
) -> list[dict]:
    """
    Parse a Goethe-Institut page for exam appointments.

    Args:
        html_content: Raw HTML of the page
        country_code: Country ISO code
        city: City name
        exam_type_filter: "ALL" or specific type like "B2"
    """
    if not html_content:
        return []

    logger.info(
        f"Parse: {city} ({country_code}), Filter={exam_type_filter}, "
        f"{len(html_content)} Zeichen"
    )

    appointments = []

    # Extract links (for booking URLs)
    links = _extract_links(html_content)
    booking_links = {}
    for href, text in links:
        combined = f"{href} {text}".lower()
        if any(kw in combined for kw in ["anmeld", "book", "regist", "kurs", "webshop"]):
            for match in EXAM_PATTERN.finditer(text):
                booking_links[match.group(1).upper()] = href

    # Also check for generic registration links
    generic_booking_url = ""
    for href, text in links:
        combined = f"{href} {text}".lower()
        if any(kw in combined for kw in ["anmeldung", "registration", "webshop", "buchen"]):
            generic_booking_url = href
            break

    logger.debug(f"Booking-Links: {booking_links}")
    if generic_booking_url:
        logger.debug(f"Generischer Booking-Link: {generic_booking_url}")

    # Convert to text
    text_content = _clean_html_to_text(html_content)

    # Log text preview
    preview = text_content[:800].strip()
    logger.info(f"Seitentext-Vorschau:\n{preview}")

    # Find all exam types, dates, times in the full text
    all_exams = list(set(m.upper() for m in EXAM_PATTERN.findall(text_content)))
    all_dates = DATE_PATTERN.findall(text_content)
    all_times = [t[0] if isinstance(t, tuple) else t for t in TIME_PATTERN.findall(text_content)]
    all_prices = PRICE_PATTERN.findall(text_content)

    logger.info(
        f"Gefunden: Prüfungen={all_exams}, Daten={all_dates[:5]}, "
        f"Zeiten={all_times[:5]}, Preise={len(all_prices)}"
    )

    # Check overall availability
    text_lower = text_content.lower()
    has_available = any(kw in text_lower for kw in AVAILABLE_KEYWORDS)
    has_unavailable = any(kw in text_lower for kw in UNAVAILABLE_KEYWORDS)

    # Strategy 1: Scan text blocks for exam+date combos
    blocks = re.split(r"\n{2,}", text_content)
    for block in blocks:
        block = block.strip()
        if len(block) < 5:
            continue

        block_exams = [m.upper() for m in EXAM_PATTERN.findall(block)]
        block_dates = DATE_PATTERN.findall(block)

        if not block_exams:
            continue

        # Apply filter
        if exam_type_filter != "ALL":
            block_exams = [e for e in block_exams if e == exam_type_filter]
            if not block_exams:
                continue

        block_lower = block.lower()
        block_times = [t[0] if isinstance(t, tuple) else t for t in TIME_PATTERN.findall(block)]

        if any(kw in block_lower for kw in UNAVAILABLE_KEYWORDS):
            slots = "Ausgebucht"
        elif any(kw in block_lower for kw in AVAILABLE_KEYWORDS):
            slots = "Verfügbar"
        else:
            slots = "Unbekannt"

        for exam_type in set(block_exams):
            if block_dates:
                for date in block_dates:
                    appointments.append({
                        "country_code": country_code,
                        "city": city,
                        "exam_type": exam_type,
                        "exam_date": date,
                        "exam_time": block_times[0] if block_times else "",
                        "slots_available": slots,
                        "booking_url": booking_links.get(exam_type, generic_booking_url),
                    })
            else:
                appointments.append({
                    "country_code": country_code,
                    "city": city,
                    "exam_type": exam_type,
                    "exam_date": "Siehe Website",
                    "exam_time": "",
                    "slots_available": slots,
                    "booking_url": booking_links.get(exam_type, generic_booking_url),
                })

    # Strategy 2: If specific exam page and no block matches, use full text data
    if not appointments and exam_type_filter != "ALL":
        if all_dates:
            for date in all_dates:
                appointments.append({
                    "country_code": country_code,
                    "city": city,
                    "exam_type": exam_type_filter,
                    "exam_date": date,
                    "exam_time": all_times[0] if all_times else "",
                    "slots_available": "Verfügbar" if has_available else (
                        "Ausgebucht" if has_unavailable else "Unbekannt"
                    ),
                    "booking_url": booking_links.get(exam_type_filter, generic_booking_url),
                })
        elif all_prices:
            # Page has prices listed = exam is offered here
            appointments.append({
                "country_code": country_code,
                "city": city,
                "exam_type": exam_type_filter,
                "exam_date": "Siehe Website",
                "exam_time": "",
                "slots_available": "Unbekannt",
                "booking_url": booking_links.get(exam_type_filter, generic_booking_url),
            })

    # Strategy 3: If overview page, cross-match all exams with all dates
    if not appointments and exam_type_filter == "ALL" and all_exams and all_dates:
        logger.info("Strategie 3: Kreuz-Verknüpfung von Prüfungen und Daten")
        for exam_type in all_exams:
            for date in all_dates:
                appointments.append({
                    "country_code": country_code,
                    "city": city,
                    "exam_type": exam_type,
                    "exam_date": date,
                    "exam_time": "",
                    "slots_available": "Unbekannt",
                    "booking_url": booking_links.get(exam_type, generic_booking_url),
                })

    # Deduplicate
    seen = set()
    unique = []
    for appt in appointments:
        key = (appt["country_code"], appt["city"], appt["exam_type"],
               appt["exam_date"], appt["exam_time"])
        if key not in seen:
            seen.add(key)
            unique.append(appt)

    logger.info(f"Parser-Ergebnis: {len(unique)} Termine ({city}, {country_code})")
    for appt in unique[:10]:
        logger.info(
            f"  -> {appt['exam_type']} | {appt['exam_date']} | "
            f"{appt['slots_available']} | {appt['booking_url'][:60] if appt['booking_url'] else 'kein Link'}"
        )

    return unique
