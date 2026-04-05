import aiosqlite
import logging
import os

from bot.config import DATABASE_PATH

logger = logging.getLogger(__name__)

CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id BIGINT UNIQUE NOT NULL,
    username TEXT,
    first_name TEXT,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SUBSCRIPTIONS_TABLE = """
CREATE TABLE IF NOT EXISTS subscriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL REFERENCES users(telegram_id),
    country_code TEXT NOT NULL,
    city TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, country_code, city, exam_type)
);
"""

CREATE_APPOINTMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country_code TEXT NOT NULL,
    city TEXT NOT NULL,
    exam_type TEXT NOT NULL,
    exam_date TEXT NOT NULL,
    exam_time TEXT,
    slots_available TEXT,
    booking_url TEXT,
    hash TEXT UNIQUE NOT NULL,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notified BOOLEAN DEFAULT 0
);
"""

CREATE_ALERT_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS alert_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id BIGINT NOT NULL,
    appointment_hash TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_id, appointment_hash)
);
"""


async def get_db() -> aiosqlite.Connection:
    """Get a database connection."""
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    db = await aiosqlite.connect(DATABASE_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """Initialize database tables."""
    db = await get_db()
    try:
        await db.execute(CREATE_USERS_TABLE)
        await db.execute(CREATE_SUBSCRIPTIONS_TABLE)
        await db.execute(CREATE_APPOINTMENTS_TABLE)
        await db.execute(CREATE_ALERT_HISTORY_TABLE)
        await db.commit()
        logger.info("Datenbank initialisiert.")
    finally:
        await db.close()
