import logging
from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
)

from bot import messages
from bot.keyboards import (
    country_keyboard,
    city_keyboard,
    exam_type_keyboard,
    subscription_delete_keyboard,
)
from bot.middleware import require_membership
from data.locations import LOCATIONS
from database.users import create_user
from database.subscriptions import (
    add_subscription,
    get_user_subscriptions,
    remove_subscription,
    deactivate_all_subscriptions,
)

logger = logging.getLogger(__name__)


@require_membership
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command — welcome user and show country selection."""
    user = update.effective_user
    await create_user(user.id, user.username, user.first_name)

    await update.message.reply_text(
        messages.WELCOME,
        parse_mode="MarkdownV2",
        reply_markup=country_keyboard(),
    )


@require_membership
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /hilfe command."""
    await update.message.reply_text(
        messages.HELP_TEXT, parse_mode="MarkdownV2"
    )


@require_membership
async def my_subs_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /meineabos command — list active subscriptions."""
    user = update.effective_user
    subs = await get_user_subscriptions(user.id)

    if not subs:
        await update.message.reply_text(
            messages.NO_SUBSCRIPTIONS, parse_mode="MarkdownV2"
        )
        return

    text = messages.MY_SUBSCRIPTIONS_HEADER
    for sub in subs:
        country_name = LOCATIONS.get(sub["country_code"], {}).get(
            "name", sub["country_code"]
        )
        text += messages.SUBSCRIPTION_ITEM.format(
            exam_type=sub["exam_type"],
            city=sub["city"],
            country=country_name,
        ) + "\n"
    text += "\nZum Löschen eines Abos, drücke den entsprechenden Button:"

    await update.message.reply_text(
        text,
        parse_mode="MarkdownV2",
        reply_markup=subscription_delete_keyboard(subs),
    )


@require_membership
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stop command — deactivate all subscriptions."""
    user = update.effective_user
    await deactivate_all_subscriptions(user.id)
    await update.message.reply_text(messages.ALL_STOPPED, parse_mode="MarkdownV2")


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline keyboard callbacks."""
    query = update.callback_query
    await query.answer()

    user = update.effective_user
    data = query.data

    # Check membership for callback queries too
    from bot.membership import check_channel_membership

    if not await check_channel_membership(context.bot, user.id):
        await query.edit_message_text(
            messages.CHANNEL_REQUIRED, parse_mode="MarkdownV2"
        )
        return

    if data.startswith("country:"):
        country_code = data.split(":")[1]
        await query.edit_message_text(
            messages.SELECT_CITY,
            parse_mode="MarkdownV2",
            reply_markup=city_keyboard(country_code),
        )

    elif data.startswith("city:"):
        parts = data.split(":")
        country_code = parts[1]
        city = parts[2]
        await query.edit_message_text(
            messages.SELECT_EXAM,
            parse_mode="MarkdownV2",
            reply_markup=exam_type_keyboard(country_code, city),
        )

    elif data.startswith("exam:"):
        parts = data.split(":")
        country_code = parts[1]
        city = parts[2]
        exam_type = parts[3]

        await add_subscription(user.id, country_code, city, exam_type)

        country_name = LOCATIONS.get(country_code, {}).get("name", country_code)
        await query.edit_message_text(
            messages.SUBSCRIPTION_ADDED.format(
                country=country_name, city=city, exam_type=exam_type
            ),
            parse_mode="MarkdownV2",
        )

    elif data.startswith("delete:"):
        sub_id = int(data.split(":")[1])
        removed = await remove_subscription(sub_id, user.id)
        if removed:
            await query.edit_message_text(
                messages.SUBSCRIPTION_REMOVED, parse_mode="MarkdownV2"
            )
        else:
            await query.edit_message_text(
                messages.ERROR_GENERIC, parse_mode="MarkdownV2"
            )

    elif data == "back:country":
        await query.edit_message_text(
            messages.WELCOME,
            parse_mode="MarkdownV2",
            reply_markup=country_keyboard(),
        )

    elif data.startswith("back:city:"):
        country_code = data.split(":")[2]
        await query.edit_message_text(
            messages.SELECT_CITY,
            parse_mode="MarkdownV2",
            reply_markup=city_keyboard(country_code),
        )


def register_handlers(application):
    """Register all handlers with the application."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("hilfe", help_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("meineabos", my_subs_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
