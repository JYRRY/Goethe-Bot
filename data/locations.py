"""
Goethe-Institut location data with correct URL patterns.

URL structure discovered from goethe.de:
- Egypt has city-specific pages: /ins/eg/de/sta/{city_code}/prf.html
- Other countries use: /ins/{country}/de/spr/prf.html
- Each exam type has a subpage: .../prf/gzb1.html, .../prf/gzb2.cfm, etc.
- Registration pages: .../prf/anm.html
"""

# Exam type URL suffixes used by Goethe-Institut
# Currently only monitoring B2
EXAM_URL_SUFFIXES = {
    "B2": "gzb2",    # Goethe-Zertifikat B2
}

EXAM_TYPES = ["B2"]

# Each city has its own base URL for exams
LOCATIONS = {
    "eg": {
        "name": "Ägypten",
        "cities": {
            "Kairo": {
                "base_url": "https://www.goethe.de/ins/eg/de/sta/kai/prf",
                "note": "Kairo (Dokki) und Hurghada",
            },
            "Alexandria": {
                "base_url": "https://www.goethe.de/ins/eg/de/sta/alx/prf",
                "note": "Alexandria",
            },
        },
    },
    "ma": {
        "name": "Marokko",
        "cities": {
            "Casablanca": {
                "base_url": "https://www.goethe.de/ins/ma/de/spr/prf",
                "note": "Casablanca",
            },
            "Rabat": {
                "base_url": "https://www.goethe.de/ins/ma/de/spr/prf",
                "note": "Rabat",
            },
        },
    },
    "dz": {
        "name": "Algerien",
        "cities": {
            "Algier": {
                "base_url": "https://www.goethe.de/ins/dz/de/spr/prf",
                "note": "Algier",
            },
        },
    },
    "sa": {
        "name": "Saudi-Arabien",
        "cities": {
            "Riad": {
                "base_url": "https://www.goethe.de/ins/sa/de/spr/prf",
                "note": "Riad",
            },
            "Dschidda": {
                "base_url": "https://www.goethe.de/ins/sa/de/spr/prf",
                "note": "Dschidda",
            },
        },
    },
    "lb": {
        "name": "Libanon",
        "cities": {
            "Beirut": {
                "base_url": "https://www.goethe.de/ins/lb/de/spr/prf",
                "note": "Beirut",
            },
        },
    },
}


def get_exam_urls(country_code: str, city: str) -> list[dict]:
    """
    Build all exam page URLs for a given country and city.
    Returns list of dicts with: url, exam_type, page_type
    """
    country = LOCATIONS.get(country_code)
    if not country:
        return []

    city_info = country["cities"].get(city)
    if not city_info:
        return []

    base = city_info["base_url"]
    urls = []

    # Individual exam type pages (.cfm — these contain the examfinder widget)
    for exam_type, suffix in EXAM_URL_SUFFIXES.items():
        urls.append({
            "url": f"{base}/{suffix}.cfm",
            "exam_type": exam_type,
            "page_type": "exam_detail",
        })

    return urls


def get_main_exam_url(country_code: str, city: str) -> str:
    """Get the main exam overview page URL."""
    country = LOCATIONS.get(country_code)
    if not country:
        return ""
    city_info = country["cities"].get(city)
    if not city_info:
        return ""
    return f"{city_info['base_url']}.html"


def get_country_names() -> dict[str, str]:
    """Return mapping of country_code -> display name."""
    return {code: info["name"] for code, info in LOCATIONS.items()}


def get_cities(country_code: str) -> list[str]:
    """Return list of city names for a given country code."""
    country = LOCATIONS.get(country_code)
    if not country:
        return []
    return list(country["cities"].keys())
