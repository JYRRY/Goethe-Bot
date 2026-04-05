from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from data.locations import LOCATIONS, EXAM_TYPES, get_country_names, get_cities


def country_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard for country selection."""
    buttons = []
    for code, name in get_country_names().items():
        buttons.append(
            [InlineKeyboardButton(name, callback_data=f"country:{code}")]
        )
    return InlineKeyboardMarkup(buttons)


def city_keyboard(country_code: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for city selection."""
    cities = get_cities(country_code)
    buttons = []
    for city in cities:
        buttons.append(
            [InlineKeyboardButton(city, callback_data=f"city:{country_code}:{city}")]
        )
    buttons.append(
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back:country")]
    )
    return InlineKeyboardMarkup(buttons)


def exam_type_keyboard(country_code: str, city: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for exam type selection."""
    buttons = []
    row = []
    for i, exam in enumerate(EXAM_TYPES):
        row.append(
            InlineKeyboardButton(
                exam, callback_data=f"exam:{country_code}:{city}:{exam}"
            )
        )
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append(
        [InlineKeyboardButton("⬅️ Zurück", callback_data=f"back:city:{country_code}")]
    )
    return InlineKeyboardMarkup(buttons)


def subscription_delete_keyboard(subscriptions: list[dict]) -> InlineKeyboardMarkup:
    """Build keyboard with delete buttons for each subscription."""
    buttons = []
    for sub in subscriptions:
        country_name = LOCATIONS.get(sub["country_code"], {}).get("name", sub["country_code"])
        label = f"🗑 {sub['exam_type']} - {sub['city']} ({country_name})"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"delete:{sub['id']}")]
        )
    return InlineKeyboardMarkup(buttons)
