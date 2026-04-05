import hashlib
import logging
from database.models import get_db

logger = logging.getLogger(__name__)


def compute_appointment_hash(
    country_code: str, city: str, exam_type: str, exam_date: str, exam_time: str
) -> str:
    """Generate a unique hash for an appointment."""
    key = f"{country_code}:{city}:{exam_type}:{exam_date}:{exam_time}"
    return hashlib.sha256(key.encode()).hexdigest()


async def upsert_appointment(
    country_code: str,
    city: str,
    exam_type: str,
    exam_date: str,
    exam_time: str,
    slots_available: str,
    booking_url: str,
) -> tuple[bool, str]:
    """
    Insert or update an appointment.
    Returns (is_new, hash) where is_new indicates if this is a newly discovered appointment.
    """
    appt_hash = compute_appointment_hash(
        country_code, city, exam_type, exam_date, exam_time
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
                    booking_url = ?
                WHERE hash = ?
                """,
                (slots_available, booking_url, appt_hash),
            )
            await db.commit()
            return False, appt_hash
        else:
            await db.execute(
                """
                INSERT INTO appointments
                (country_code, city, exam_type, exam_date, exam_time,
                 slots_available, booking_url, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    country_code,
                    city,
                    exam_type,
                    exam_date,
                    exam_time,
                    slots_available,
                    booking_url,
                    appt_hash,
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
