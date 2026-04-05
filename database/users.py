import logging
from database.models import get_db

logger = logging.getLogger(__name__)


async def create_user(telegram_id: int, username: str | None, first_name: str | None):
    """Create or update a user record."""
    db = await get_db()
    try:
        await db.execute(
            """
            INSERT INTO users (telegram_id, username, first_name, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(telegram_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_active = 1
            """,
            (telegram_id, username, first_name),
        )
        await db.commit()
        logger.info(f"Benutzer erstellt/aktualisiert: {telegram_id}")
    finally:
        await db.close()


async def get_user(telegram_id: int) -> dict | None:
    """Get a user by telegram ID."""
    db = await get_db()
    try:
        cursor = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
        )
        row = await cursor.fetchone()
        if row:
            return dict(row)
        return None
    finally:
        await db.close()


async def set_user_active(telegram_id: int, active: bool):
    """Set user active status."""
    db = await get_db()
    try:
        await db.execute(
            "UPDATE users SET is_active = ? WHERE telegram_id = ?",
            (active, telegram_id),
        )
        await db.commit()
    finally:
        await db.close()
