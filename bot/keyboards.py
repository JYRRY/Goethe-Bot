from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from data.locations import LOCATIONS, get_country_names


def country_keyboard() -> InlineKeyboardMarkup:
    """Build inline keyboard for country selection."""
    buttons = []
    for code, name in get_country_names().items():
        buttons.append(
            [InlineKeyboardButton(name, callback_data=f"country:{code}")]
        )
    return InlineKeyboardMarkup(buttons)


def city_keyboard(country_code: str) -> InlineKeyboardMarkup:
    """Build inline keyboard for city selection. Subscribes directly to B2."""
    country = LOCATIONS.get(country_code, {})
    cities_data = country.get("cities", {})
    buttons = []
    for city_name, city_info in cities_data.items():
        note = city_info.get("note", city_name)
        display = note if note != city_name else city_name
        # Directly subscribe to B2 when city is selected
        buttons.append(
            [InlineKeyboardButton(
                display,
                callback_data=f"subscribe:{country_code}:{city_name}:B2",
            )]
        )
    buttons.append(
        [InlineKeyboardButton("⬅️ Zurück", callback_data="back:country")]
    )
    return InlineKeyboardMarkup(buttons)


def announced_appointment_keyboard(appt_hash: str, exam_date: str, booking_opens: str) -> InlineKeyboardMarkup:
    """Build keyboard with a watch button for an announced appointment."""
    label = f"🔔 Erinnere mich am {booking_opens}"
    buttons = [
        [InlineKeyboardButton(label, callback_data=f"watch:{appt_hash}")]
    ]
    return InlineKeyboardMarkup(buttons)


def subscription_delete_keyboard(subscriptions: list[dict]) -> InlineKeyboardMarkup:
    """Build keyboard with delete buttons for each subscription."""
    buttons = []
    for sub in subscriptions:
        country_name = LOCATIONS.get(sub["country_code"], {}).get("name", sub["country_code"])
        label = f"🗑 B2 - {sub['city']} ({country_name})"
        buttons.append(
            [InlineKeyboardButton(label, callback_data=f"delete:{sub['id']}")]
        )
    return InlineKeyboardMarkup(buttons)
