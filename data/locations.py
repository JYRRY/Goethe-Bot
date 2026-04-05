LOCATIONS = {
    "eg": {
        "name": "Ägypten",
        "cities": {
            "Alexandria": "alexandria",
            "Dokki": "dokki",
            "Hurghada": "hurghada",
        },
    },
    "ma": {
        "name": "Marokko",
        "cities": {
            "Casablanca": "casablanca",
            "Rabat": "rabat",
        },
    },
    "dz": {
        "name": "Algerien",
        "cities": {
            "Algier": "algier",
        },
    },
    "sa": {
        "name": "Saudi-Arabien",
        "cities": {
            "Riad": "riad",
            "Dschidda": "dschidda",
        },
    },
    "lb": {
        "name": "Libanon",
        "cities": {
            "Beirut": "beirut",
        },
    },
}

EXAM_TYPES = ["A1", "A2", "B1", "B2", "C1", "C2"]


def get_exam_url(country_code: str) -> str:
    """Build the Goethe-Institut exam dates URL for a given country."""
    return f"https://www.goethe.de/ins/{country_code}/de/prf/ter.html"


def get_country_names() -> dict[str, str]:
    """Return mapping of country_code -> display name."""
    return {code: info["name"] for code, info in LOCATIONS.items()}


def get_cities(country_code: str) -> list[str]:
    """Return list of city names for a given country code."""
    country = LOCATIONS.get(country_code)
    if not country:
        return []
    return list(country["cities"].keys())
