"""Start and help command handlers with subscription checking."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from app import texts
from app.config import settings
from app.db import upsert_user
from app.services.subscription import check_user_subscriptions, get_subscription_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    """Handle /start command, register user, verify sponsor subscriptions."""
    if not message.from_user:
        return

    await upsert_user(
        db_path=settings.db_path,
        user_id=message.from_user.id,
        username=message.from_user.username,
    )

    # Verify sponsor channel subscriptions
    is_sub, unsub = await check_user_subscriptions(
        bot=message.bot,
        user_id=message.from_user.id,
        db_path=settings.db_path,
    )

    if not is_sub:
        keyboard = get_subscription_keyboard(unsub)
        await message.answer(texts.SUB_REQUIRED, reply_markup=keyboard, parse_mode="HTML")
        return

    await message.answer(texts.START_WELCOME, parse_mode="HTML")


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    """Handle /help command with instructions and limits."""
    if message.from_user:
        await upsert_user(
            db_path=settings.db_path,
            user_id=message.from_user.id,
            username=message.from_user.username,
        )

    await message.answer(texts.HELP_MESSAGE, parse_mode="HTML")


@router.callback_query(F.data == "sub:check")
async def callback_check_subscription(callback: CallbackQuery) -> None:
    """Verify if user has joined all required sponsor channels."""
    if not callback.from_user or not callback.message:
        return

    is_sub, unsub = await check_user_subscriptions(
        bot=callback.bot,
        user_id=callback.from_user.id,
        db_path=settings.db_path,
    )

    if is_sub:
        await callback.message.edit_text(texts.SUB_CHECK_SUCCESS, parse_mode="HTML")
        await callback.answer()
    else:
        await callback.answer(texts.SUB_CHECK_FAIL, show_alert=True)
        # Update buttons with currently remaining unsubscribed channels
        await callback.message.edit_reply_markup(reply_markup=get_subscription_keyboard(unsub))
