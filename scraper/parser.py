import logging
import re

logger = logging.getLogger(__name__)


# Exam level patterns
EXAM_PATTERN = re.compile(
    r"\b(?:Goethe-Zertifikat\s+)?(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE
)

# Date patterns (DD.MM.YYYY or YYYY-MM-DD or DD. Month YYYY)
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}\.\s*(?:Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s+\d{4})\b"
)

# Time pattern (HH:MM)
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2})\s*(?:Uhr)?\b")

# Availability keywords
AVAILABLE_KEYWORDS = [
    "verfügbar", "available", "freie plätze", "free places",
    "anmelden", "register", "buchen", "book", "plätze frei",
    "zur anmeldung", "jetzt anmelden", "noch plätze",
]

UNAVAILABLE_KEYWORDS = [
    "ausgebucht", "fully booked", "keine plätze", "no places",
    "warteliste", "waiting list", "sold out", "nicht verfügbar",
    "belegt", "abgesagt", "cancelled",
]


def parse_appointments(
    html_content: str, country_code: str, target_cities: list[str]
) -> list[dict]:
    """
    Parse Goethe-Institut exam page HTML and extract appointments.
    Uses multiple strategies to find appointment data.
    """
    if not html_content:
        logger.warning(f"Leerer HTML-Inhalt für {country_code}")
        return []

    logger.info(f"Parse HTML für {country_code}: {len(html_content)} Zeichen")

    appointments = []

    # Remove script and style tags
    clean_html = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
    clean_html = re.sub(r"<style[^>]*>.*?</style>", "", clean_html, flags=re.DOTALL)

    # Extract all links with href for booking URLs
    link_pattern = re.compile(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    links = link_pattern.findall(clean_html)
    booking_links = {}
    all_links_with_exam = []

    for href, text in links:
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        for exam_match in EXAM_PATTERN.finditer(clean_text):
            exam_type = exam_match.group(1).upper()
            if not href.startswith("http"):
                href = f"https://www.goethe.de{href}"
            all_links_with_exam.append((exam_type, href, clean_text))
            if any(kw in href.lower() for kw in ["anmeld", "book", "regist", "kurs"]):
                booking_links[exam_type] = href

    if all_links_with_exam:
        logger.info(f"Links mit Prüfungstyp gefunden: {len(all_links_with_exam)}")
        for exam_type, href, text in all_links_with_exam[:5]:
            logger.debug(f"  Link: {exam_type} -> {href} ({text[:50]})")

    # Clean HTML to text
    text_content = re.sub(r"<[^>]+>", "\n", clean_html)
    text_content = re.sub(r"&nbsp;", " ", text_content)
    text_content = re.sub(r"&amp;", "&", text_content)
    text_content = re.sub(r"&[a-z]+;", "", text_content)
    text_content = re.sub(r"\n{3,}", "\n\n", text_content)

    # Log a snippet of the text content for debugging
    text_preview = text_content[:500].strip()
    logger.info(f"Text-Vorschau ({country_code}):\n{text_preview}")

    # Split into blocks
    blocks = re.split(r"\n{2,}", text_content)
    logger.info(f"Textblöcke: {len(blocks)}")

    # Count how many blocks mention exam types
    exam_blocks = 0
    for block in blocks:
        if EXAM_PATTERN.search(block):
            exam_blocks += 1
    logger.info(f"Blöcke mit Prüfungstyp: {exam_blocks}")

    # Strategy 1: Block-based parsing
    for block in blocks:
        block = block.strip()
        if len(block) < 5:
            continue

        exam_matches = EXAM_PATTERN.findall(block)
        if not exam_matches:
            continue

        dates = DATE_PATTERN.findall(block)
        times = TIME_PATTERN.findall(block)

        block_lower = block.lower()
        is_available = any(kw in block_lower for kw in AVAILABLE_KEYWORDS)
        is_unavailable = any(kw in block_lower for kw in UNAVAILABLE_KEYWORDS)

        if is_unavailable:
            slots = "Ausgebucht"
        elif is_available:
            slots = "Verfügbar"
        else:
            slots = "Unbekannt"

        mentioned_city = None
        for city in target_cities:
            if city.lower() in block_lower:
                mentioned_city = city
                break

        for exam_type in exam_matches:
            if isinstance(exam_type, tuple):
                exam_type = exam_type[0] if exam_type[0] else exam_type[1]
            exam_type = exam_type.upper()

            if dates:
                for date in dates:
                    time_str = times[0] if times else ""
                    if isinstance(time_str, tuple):
                        time_str = time_str[0]
                    appointments.append({
                        "country_code": country_code,
                        "city": mentioned_city or (target_cities[0] if target_cities else ""),
                        "exam_type": exam_type,
                        "exam_date": date,
                        "exam_time": time_str,
                        "slots_available": slots,
                        "booking_url": booking_links.get(exam_type, ""),
                    })
            else:
                # No date found but exam type exists - still record it
                appointments.append({
                    "country_code": country_code,
                    "city": mentioned_city or (target_cities[0] if target_cities else ""),
                    "exam_type": exam_type,
                    "exam_date": "Siehe Website",
                    "exam_time": "",
                    "slots_available": slots,
                    "booking_url": booking_links.get(exam_type, ""),
                })

    # Strategy 2: If no appointments found via blocks, try scanning the full text
    if not appointments:
        logger.info("Strategie 1 fand nichts. Versuche Strategie 2 (Volltext-Scan)...")

        all_exams = EXAM_PATTERN.findall(text_content)
        all_dates = DATE_PATTERN.findall(text_content)

        logger.info(
            f"Volltext: {len(all_exams)} Prüfungstypen, "
            f"{len(all_dates)} Daten gefunden"
        )

        if all_exams and all_dates:
            for exam_type in all_exams:
                if isinstance(exam_type, tuple):
                    exam_type = exam_type[0] if exam_type[0] else exam_type[1]
                exam_type = exam_type.upper()

                for date in all_dates:
                    appointments.append({
                        "country_code": country_code,
                        "city": target_cities[0] if target_cities else "",
                        "exam_type": exam_type,
                        "exam_date": date,
                        "exam_time": "",
                        "slots_available": "Unbekannt",
                        "booking_url": booking_links.get(exam_type, ""),
                    })
        elif all_exams:
            # Found exam types but no dates
            for exam_type in all_exams:
                if isinstance(exam_type, tuple):
                    exam_type = exam_type[0] if exam_type[0] else exam_type[1]
                exam_type = exam_type.upper()

                appointments.append({
                    "country_code": country_code,
                    "city": target_cities[0] if target_cities else "",
                    "exam_type": exam_type,
                    "exam_date": "Siehe Website",
                    "exam_time": "",
                    "slots_available": "Unbekannt",
                    "booking_url": booking_links.get(exam_type, ""),
                })

    # Strategy 3: If still nothing, use links that mention exam types
    if not appointments and all_links_with_exam:
        logger.info("Strategie 2 fand nichts. Versuche Strategie 3 (Link-Analyse)...")
        for exam_type, href, link_text in all_links_with_exam:
            dates = DATE_PATTERN.findall(link_text)
            appointments.append({
                "country_code": country_code,
                "city": target_cities[0] if target_cities else "",
                "exam_type": exam_type,
                "exam_date": dates[0] if dates else "Siehe Website",
                "exam_time": "",
                "slots_available": "Unbekannt",
                "booking_url": href,
            })

    # Deduplicate
    seen = set()
    unique_appointments = []
    for appt in appointments:
        key = (
            appt["country_code"],
            appt["city"],
            appt["exam_type"],
            appt["exam_date"],
            appt["exam_time"],
        )
        if key not in seen:
            seen.add(key)
            unique_appointments.append(appt)

    logger.info(
        f"Parser-Ergebnis: {len(unique_appointments)} eindeutige Termine "
        f"({country_code})"
    )
    for appt in unique_appointments[:5]:
        logger.info(
            f"  -> {appt['exam_type']} | {appt['exam_date']} | "
            f"{appt['city']} | {appt['slots_available']}"
        )

    return unique_appointments
