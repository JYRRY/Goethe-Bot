import logging
from database.models import get_db

logger = logging.getLogger(__name__)


async def add_subscription(
    user_id: int, country_code: str, city: str, exam_type: str
) -> bool:
    """Add a new subscription. Returns True if created, False if already exists."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO subscriptions (user_id, country_code, city, exam_type, is_active)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, country_code, city, exam_type) DO UPDATE SET
                is_active = 1
            """,
            (user_id, country_code, city, exam_type),
        )
        await db.commit()
        logger.info(
            f"Abo hinzugefügt: user={user_id}, {country_code}/{city}/{exam_type}"
        )
        return True
    finally:
        await db.close()


async def get_user_subscriptions(user_id: int) -> list[dict]:
    """Get all active subscriptions for a user."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT * FROM subscriptions
            WHERE user_id = ? AND is_active = 1
            ORDER BY created_at DESC
            """,
            (user_id,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def remove_subscription(subscription_id: int, user_id: int) -> bool:
    """Deactivate a subscription."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            UPDATE subscriptions SET is_active = 0
            WHERE id = ? AND user_id = ?
            """,
            (subscription_id, user_id),
        )
        await db.commit()
        return cursor.rowcount > 0
    finally:
        await db.close()


async def deactivate_all_subscriptions(user_id: int):
    """Deactivate all subscriptions for a user."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE subscriptions SET is_active = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()
        logger.info(f"Alle Abos deaktiviert für user={user_id}")
    finally:
        await db.close()


async def get_active_locations() -> list[dict]:
    """Get all unique (country_code, city) pairs that have active subscriptions."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT DISTINCT country_code, city
            FROM subscriptions
            WHERE is_active = 1
            """
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
    finally:
        await db.close()


async def get_subscribers_for_appointment(
    country_code: str, city: str, exam_type: str
) -> list[int]:
    """Get all user IDs subscribed to a specific location + exam type."""
    db = await get_db()
    try:
        cursor = await db.execute(
            """
            SELECT DISTINCT s.user_id
            FROM subscriptions s
            JOIN users u ON u.telegram_id = s.user_id
            WHERE s.country_code = ?
              AND s.city = ?
              AND s.exam_type = ?
              AND s.is_active = 1
              AND u.is_active = 1
            """,
            (country_code, city, exam_type),
        )
        rows = await cursor.fetchall()
        return [row["user_id"] for row in rows]
    finally:
        await db.close()
