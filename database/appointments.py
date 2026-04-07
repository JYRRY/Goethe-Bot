import hashlib
import logging
from database.models import get_db

logger = logging.getLogger(__name__)


def compute_appointment_hash(
    country_code: str, city: str, exam_type: str, exam_date: str, exam_parts: str
) -> str:
    """Generate a unique hash for an appointment."""
    key = f"{country_code}:{city}:{exam_type}:{exam_date}:{exam_parts}"
    return hashlib.sha256(key.encode()).hexdigest()


async def upsert_appointment(
    country_code: str,
    city: str,
    exam_type: str,
    exam_date: str,
    exam_parts: str,
    slots_available: str,
    booking_url: str,
    booking_opens: str = "",
    price: str = "",
) -> tuple[bool, str]:
    """
    Insert or update an appointment.
    Returns (is_new, hash) where is_new indicates if this is a newly discovered appointment.
    """
    appt_hash = compute_appointment_hash(
        country_code, city, exam_type, exam_date, exam_parts
    )
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT id, notified FROM appointments WHERE hash = ?", (appt_hash,)
        )
        existing = await cursor.fetchone()

        if existing:
            await db.execute(
                """
                UPDATE appointments
                SET last_seen_at = CURRENT_TIMESTAMP,
                    slots_available = ?,
                    booking_url = ?,
                    booking_opens = ?,
                    price = ?
                WHERE hash = ?
                """,
                (slots_available, booking_url, booking_opens, price, appt_hash),
            )
            await db.commit()
            return False, appt_hash
        else:
            await db.execute(
                """
                INSERT INTO appointments
                (country_code, city, exam_type, exam_date, exam_time,
                 exam_parts, slots_available, booking_url, hash,
                 booking_opens, price)
                VALUES (?, ?, ?, ?, '', ?, ?, ?, ?, ?, ?)
                """,
                (
                    country_code,
                    city,
                    exam_type,
                    exam_date,
                    exam_parts,
                    slots_available,
                    booking_url,
                    appt_hash,
                    booking_opens,
                    price,
                ),
            )
            await db.commit()
            logger.info(
                f"Neuer Termin: {exam_type} in {city} ({country_code}) am {exam_date}"
            )
            return True, appt_hash
    finally:
        await db.close()


async def mark_notified(appt_hash: str):
    """Mark an appointment as notified."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE appointments SET notified = 1 WHERE hash = ?", (appt_hash,)
        )
        await db.commit()
    finally:
        await db.close()


async def record_alert(user_id: int, appointment_hash: str):
    """Record that an alert was sent to a user for an appointment."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT OR IGNORE INTO alert_history (user_id, appointment_hash)
            VALUES (?, ?)
            """,
            (user_id, appointment_hash),
        )
        await db.commit()
    finally:
        await db.close()


async def was_user_alerted(user_id: int, appointment_hash: str) -> bool:
    """Check if a user was already alerted for an appointment."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT 1 FROM alert_history WHERE user_id = ? AND appointment_hash = ?",
            (user_id, appointment_hash),
        )
        return await cursor.fetchone() is not None
    finally:
        await db.close()


# ------------------------------------------------------------------
# Booking watches — user-selected "Anmeldung ab" reminders
# ------------------------------------------------------------------

async def add_booking_watch(
    user_id: int,
    appt_hash: str,
    exam_date: str,
    booking_opens: str,
    city: str,
    country_code: str,
) -> bool:
    """Add a booking watch for a user. Returns True if created."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT OR IGNORE INTO booking_watches
            (user_id, appointment_hash, exam_date, booking_opens, city, country_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (user_id, appt_hash, exam_date, booking_opens, city, country_code),
        )
        await db.commit()
        return True
    finally:
        await db.close()


async def get_due_booking_watches() -> list[dict]:
    """Get all booking watches where booking_opens date has arrived."""
    from datetime import date as date_cls
    today = date_cls.today().strftime("%d.%m.%Y")
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT * FROM booking_watches
            WHERE reminded = 0
            """
        )
        rows = await cursor.fetchall()
        due = []
        for row in rows:
            row_dict = dict(row)
            # Parse DD.MM.YYYY and compare with today
            try:
                parts = row_dict["booking_opens"].split(".")
                opens_date = date_cls(int(parts[2]), int(parts[1]), int(parts[0]))
                if opens_date <= date_cls.today():
                    due.append(row_dict)
            except (ValueError, IndexError):
                continue
        return due
    finally:
        await db.close()


async def mark_watch_reminded(watch_id: int):
    """Mark a booking watch as reminded."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE booking_watches SET reminded = 1 WHERE id = ?",
            (watch_id,),
        )
        await db.commit()
    finally:
        await db.close()


async def get_appointment_by_hash(appt_hash: str) -> dict | None:
    """Get appointment details by hash."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM appointments WHERE hash = ?", (appt_hash,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()
