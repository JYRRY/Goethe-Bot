import logging
import re
from html.parser import HTMLParser

logger = logging.getLogger(__name__)


class AppointmentHTMLParser(HTMLParser):
    """Parse Goethe-Institut exam appointment pages.

    The Goethe website structure varies by country, so this parser uses
    multiple strategies to extract appointment data:
    1. Look for structured exam listing elements (tables, cards, lists)
    2. Extract exam type, date, time, location, and booking URLs
    3. Match against the target cities filter
    """

    def __init__(self, country_code: str, target_cities: list[str]):
        super().__init__()
        self.country_code = country_code
        self.target_cities = [c.lower() for c in target_cities]
        self.appointments = []

        # Parser state
        self._current_tag = ""
        self._current_attrs = {}
        self._text_buffer = ""
        self._in_exam_section = False
        self._current_appointment = {}
        self._all_text_blocks = []
        self._links = []

    def handle_starttag(self, tag, attrs):
        self._current_tag = tag
        self._current_attrs = dict(attrs)

        # Track links for booking URLs
        if tag == "a":
            href = self._current_attrs.get("href", "")
            if href:
                self._links.append(href)

        # Detect exam-related sections by class/id
        cls = self._current_attrs.get("class", "")
        id_attr = self._current_attrs.get("id", "")

        exam_indicators = [
            "pruefung", "prüfung", "exam", "termin", "appointment",
            "test-date", "buchung", "booking", "anmeldung", "registration",
        ]

        combined = f"{cls} {id_attr}".lower()
        if any(ind in combined for ind in exam_indicators):
            self._in_exam_section = True

    def handle_endtag(self, tag):
        if self._text_buffer.strip():
            self._all_text_blocks.append(self._text_buffer.strip())
        self._text_buffer = ""

        if tag in ("div", "section", "article", "tr"):
            if self._in_exam_section and self._current_appointment:
                self.appointments.append(self._current_appointment.copy())
                self._current_appointment = {}
            self._in_exam_section = False

    def handle_data(self, data):
        self._text_buffer += data


# Exam level patterns
EXAM_PATTERN = re.compile(
    r"\b(Goethe-Zertifikat\s+)?(A1|A2|B1|B2|C1|C2)\b", re.IGNORECASE
)

# Date patterns (DD.MM.YYYY or YYYY-MM-DD)
DATE_PATTERN = re.compile(
    r"\b(\d{1,2}\.\d{1,2}\.\d{4}|\d{4}-\d{2}-\d{2})\b"
)

# Time pattern (HH:MM)
TIME_PATTERN = re.compile(r"\b(\d{1,2}:\d{2})\s*(Uhr)?\b")

# Availability keywords
AVAILABLE_KEYWORDS = [
    "verfügbar", "available", "freie plätze", "free places",
    "anmelden", "register", "buchen", "book", "plätze frei",
]

UNAVAILABLE_KEYWORDS = [
    "ausgebucht", "fully booked", "keine plätze", "no places",
    "warteliste", "waiting list", "sold out",
]


def parse_appointments(
    html_content: str, country_code: str, target_cities: list[str]
) -> list[dict]:
    """
    Parse Goethe-Institut exam page HTML and extract appointments.

    Uses a text-based approach: scans all text content for exam types,
    dates, and availability indicators, then correlates them.
    """
    appointments = []

    # Strategy: split content into logical blocks and scan each
    # Remove HTML tags but keep structure hints
    text_content = re.sub(r"<script[^>]*>.*?</script>", "", html_content, flags=re.DOTALL)
    text_content = re.sub(r"<style[^>]*>.*?</style>", "", html_content, flags=re.DOTALL)

    # Extract all links with href
    link_pattern = re.compile(r'<a[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.DOTALL)
    links = link_pattern.findall(html_content)
    booking_links = {}
    for href, text in links:
        clean_text = re.sub(r"<[^>]+>", "", text).strip()
        for exam_match in EXAM_PATTERN.finditer(clean_text):
            exam_type = exam_match.group(2).upper()
            if "anmeld" in href.lower() or "book" in href.lower() or "regist" in href.lower():
                if not href.startswith("http"):
                    href = f"https://www.goethe.de{href}"
                booking_links[exam_type] = href

    # Clean HTML to text
    clean_text = re.sub(r"<[^>]+>", "\n", html_content)
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)

    # Split into blocks (paragraphs, sections)
    blocks = re.split(r"\n{2,}", clean_text)

    city_lower = [c.lower() for c in target_cities]

    for block in blocks:
        block = block.strip()
        if len(block) < 10:
            continue

        # Find exam types mentioned in this block
        exam_matches = EXAM_PATTERN.findall(block)
        if not exam_matches:
            continue

        # Find dates
        dates = DATE_PATTERN.findall(block)

        # Check availability
        block_lower = block.lower()
        is_available = any(kw in block_lower for kw in AVAILABLE_KEYWORDS)
        is_unavailable = any(kw in block_lower for kw in UNAVAILABLE_KEYWORDS)

        # Determine slots text
        if is_unavailable:
            slots = "Ausgebucht"
        elif is_available:
            slots = "Verfügbar"
        else:
            slots = "Unbekannt"

        # Find times
        times = TIME_PATTERN.findall(block)

        # Check if any target city is mentioned
        mentioned_city = None
        for city in target_cities:
            if city.lower() in block_lower:
                mentioned_city = city
                break

        # For each exam type + date combination found, create an appointment
        for _, exam_type in exam_matches:
            exam_type = exam_type.upper()

            if not dates:
                dates = ["Siehe Website"]

            for date in dates:
                time_str = times[0][0] if times else ""
                booking_url = booking_links.get(exam_type, "")

                appointment = {
                    "country_code": country_code,
                    "city": mentioned_city or (target_cities[0] if target_cities else ""),
                    "exam_type": exam_type,
                    "exam_date": date,
                    "exam_time": time_str,
                    "slots_available": slots,
                    "booking_url": booking_url,
                }
                appointments.append(appointment)

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
        f"Parser: {len(unique_appointments)} eindeutige Termine "
        f"aus {len(blocks)} Textblöcken extrahiert ({country_code})"
    )
    return unique_appointments
