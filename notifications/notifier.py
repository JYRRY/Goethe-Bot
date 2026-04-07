import asyncio
import logging
from telegram import Bot
from telegram.error import TelegramError

from bot import messages
from bot.keyboards import announced_appointment_keyboard
from data.locations import LOCATIONS
from database.appointments import was_user_alerted, record_alert, mark_notified
from database.subscriptions import get_subscribers_for_appointment

logger = logging.getLogger(__name__)

SEND_DELAY = 0.05  # 50ms between messages


def _escape_md(text: str) -> str:
    """Escape special characters for MarkdownV2."""
    special = r"_*[]()~`>#+-=|{}.!"
    for char in special:
        text = text.replace(char, f"\\{char}")
    return text


async def notify_new_appointment(bot: Bot, appointment: dict, appt_hash: str):
    """Send notifications to all subscribers for a new appointment."""
    country_code = appointment["country_code"]
    city = appointment["city"]
    exam_type = appointment["exam_type"]

    subscribers = await get_subscribers_for_appointment(
        country_code, city, exam_type
    )

    if not subscribers:
        logger.debug(
            f"Keine Abonnenten für {exam_type} in {city} ({country_code})"
        )
        return

    country_name = LOCATIONS.get(country_code, {}).get("name", country_code)

    # Build conditional price line
    price = appointment.get("price", "")
    price_line = f"💰 Preis: {_escape_md(price)}\n" if price else ""

    booking_url = appointment.get("booking_url", "")
    booking_opens = appointment.get("booking_opens", "")

    sent_count = 0
    for user_id in subscribers:
        if await was_user_alerted(user_id, appt_hash):
            continue

        fmt_kwargs = {
            "date": _escape_md(appointment.get("exam_date", "N/A")),
            "city": _escape_md(city),
            "country": _escape_md(country_name),
            "exam_parts": _escape_md(
                appointment.get("exam_parts", "") or "Nicht angegeben"
            ),
            "price_line": price_line,
            "slots": _escape_md(appointment.get("slots_available", "Unbekannt")),
        }

        reply_markup = None

        if booking_opens:
            fmt_kwargs["booking_opens"] = _escape_md(booking_opens)
            text = messages.APPOINTMENT_ANNOUNCED.format(**fmt_kwargs)
            # Add watch button for announced appointments
            reply_markup = announced_appointment_keyboard(
                appt_hash,
                appointment.get("exam_date", ""),
                booking_opens,
            )
        elif booking_url:
            fmt_kwargs["booking_url"] = booking_url
            text = messages.APPOINTMENT_ALERT_WITH_LINK.format(**fmt_kwargs)
        else:
            text = messages.APPOINTMENT_ALERT.format(**fmt_kwargs)

        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="MarkdownV2",
                disable_web_page_preview=True,
                reply_markup=reply_markup,
            )
            await record_alert(user_id, appt_hash)
            sent_count += 1
            await asyncio.sleep(SEND_DELAY)
        except TelegramError as e:
            logger.warning(
                f"Nachricht an {user_id} fehlgeschlagen: {e}"
            )

    if sent_count > 0:
        await mark_notified(appt_hash)
        logger.info(
            f"Benachrichtigung gesendet: {exam_type} in {city} ({country_code}) "
            f"an {sent_count} Benutzer"
        )
