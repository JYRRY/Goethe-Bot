import functools
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.membership import check_channel_membership
from bot import messages

logger = logging.getLogger(__name__)


def require_membership(func):
    """Decorator that checks channel membership before executing a handler."""

    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return

        is_member = await check_channel_membership(context.bot, user.id)
        if not is_member:
            await update.effective_message.reply_text(
                messages.CHANNEL_REQUIRED, parse_mode="MarkdownV2"
            )
            return

        return await func(update, context)

    return wrapper
