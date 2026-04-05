import logging
from telegram import Bot
from telegram.error import TelegramError

from bot.config import REQUIRED_CHANNEL_ID

logger = logging.getLogger(__name__)

ALLOWED_STATUSES = {"member", "administrator", "creator"}


async def check_channel_membership(bot: Bot, user_id: int) -> bool:
    """Check if a user is a member of the required channel."""
    try:
        member = await bot.get_chat_member(
            chat_id=REQUIRED_CHANNEL_ID, user_id=user_id
        )
        is_member = member.status in ALLOWED_STATUSES
        if not is_member:
            logger.info(
                f"Benutzer {user_id} ist kein Mitglied von {REQUIRED_CHANNEL_ID} "
                f"(Status: {member.status})"
            )
        return is_member
    except TelegramError as e:
        logger.warning(
            f"Fehler bei Mitgliedschaftsprüfung für {user_id}: {e}"
        )
        return False
