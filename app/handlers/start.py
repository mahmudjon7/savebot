"""Start, help, subscription check, and join-request handlers."""

from typing import List, Optional
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, ChatJoinRequest, ChatMemberUpdated, Message

from app import texts
from app.config import settings
from app.db import (
    add_join_request,
    get_channels,
    is_known_user,
    register_referral,
    remove_join_request,
    upsert_user,
)
from app.services.referral import (
    confirm_and_notify,
    parse_ref_payload,
    referral_menu_keyboard,
    render_my_referrals,
    render_top,
)
from app.services.subscription import (
    check_user_subscriptions,
    get_subscription_keyboard,
    parse_channel_identifier,
)

router = Router(name="start")


def _chat_candidate_ids(chat_id: int, username: Optional[str]) -> List[str]:
    """Build canonical channel identifier strings for matching DB records."""
    ids = [str(chat_id)]
    if username:
        ids.append(f"@{username.lower()}")
        ids.append(f"@{username}")
    return list(dict.fromkeys(ids))


async def _matching_channel_ids(chat_id: int, username: Optional[str]) -> List[str]:
    """Return matching DB channel identifiers for a Telegram chat, or empty list if not a sponsor."""
    candidates = _chat_candidate_ids(chat_id, username)
    candidate_set = {c.lower() for c in candidates}

    matched = False
    for ch in await get_channels(settings.db_path):
        raw_cid = str(ch["channel_id"])
        lookup_id, _ = parse_channel_identifier(raw_cid)
        if raw_cid.lower() in candidate_set or (lookup_id is not None and str(lookup_id).lower() in candidate_set):
            matched = True
            candidates.append(raw_cid)

    return list(dict.fromkeys(candidates)) if matched else []


@router.message(CommandStart())
async def handle_start(message: Message, state: FSMContext, command: Optional[CommandObject] = None) -> None:
    """Handle /start command, register user, record referral, verify sponsor subscriptions."""
    if not message.from_user:
        return

    await state.clear()

    inviter_id = parse_ref_payload(command.args if command else None)
    # Decide "new user" BEFORE we register this user, otherwise nobody would ever be new.
    was_new = inviter_id is not None and not await is_known_user(settings.db_path, message.from_user.id)

    await upsert_user(
        db_path=settings.db_path,
        user_id=message.from_user.id,
        username=message.from_user.username,
    )

    if was_new:
        await register_referral(settings.db_path, inviter_id, message.from_user.id)

    is_sub, unsub = await check_user_subscriptions(
        bot=message.bot,
        user_id=message.from_user.id,
        db_path=settings.db_path,
    )

    if not is_sub:
        keyboard = get_subscription_keyboard(unsub)
        await message.answer(texts.SUB_REQUIRED, reply_markup=keyboard, parse_mode="HTML")
        return

    await confirm_and_notify(message.bot, settings.db_path, message.from_user.id)
    await message.answer(texts.START_WELCOME, reply_markup=referral_menu_keyboard(), parse_mode="HTML")


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
        await confirm_and_notify(callback.bot, settings.db_path, callback.from_user.id)
        keyboard = referral_menu_keyboard()
        try:
            await callback.message.edit_text(texts.SUB_CHECK_SUCCESS, reply_markup=keyboard, parse_mode="HTML")
        except TelegramBadRequest as e:
            if "message is not modified" not in str(e).lower():
                await callback.message.answer(texts.SUB_CHECK_SUCCESS, reply_markup=keyboard, parse_mode="HTML")
        except Exception:
            await callback.message.answer(texts.SUB_CHECK_SUCCESS, reply_markup=keyboard, parse_mode="HTML")
        await callback.answer()
    else:
        await callback.answer(texts.SUB_CHECK_FAIL, show_alert=True)
        try:
            await callback.message.edit_reply_markup(reply_markup=get_subscription_keyboard(unsub))
        except TelegramBadRequest:
            pass


@router.message(Command("taklif"))
async def handle_invite_command(message: Message) -> None:
    """Show the user's referral link, counts and rank."""
    if not message.from_user:
        return
    await upsert_user(settings.db_path, message.from_user.id, message.from_user.username)
    text, markup = await render_my_referrals(message.bot, settings.db_path, message.from_user.id)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.message(Command("top"))
async def handle_top_command(message: Message) -> None:
    """Show the TOP inviters list."""
    if not message.from_user:
        return
    await message.answer(await render_top(settings.db_path, message.from_user.id), parse_mode="HTML")


@router.callback_query(F.data == "ref:me")
async def callback_my_referrals(callback: CallbackQuery) -> None:
    """Button: personal invite link and stats."""
    if not callback.from_user or not callback.message:
        return
    await upsert_user(settings.db_path, callback.from_user.id, callback.from_user.username)
    text, markup = await render_my_referrals(callback.bot, settings.db_path, callback.from_user.id)
    await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ref:top")
async def callback_top(callback: CallbackQuery) -> None:
    """Button: TOP inviters list."""
    if not callback.from_user or not callback.message:
        return
    await callback.message.answer(await render_top(settings.db_path, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


@router.chat_join_request()
async def handle_chat_join_request(event: ChatJoinRequest) -> None:
    """Record join requests for configured sponsor channels (for request-to-join links)."""
    if not event.from_user or not event.chat:
        return

    matched_ids = await _matching_channel_ids(event.chat.id, getattr(event.chat, "username", None))
    if matched_ids:
        await add_join_request(settings.db_path, event.from_user.id, matched_ids)


@router.chat_member()
async def handle_chat_member_update(event: ChatMemberUpdated) -> None:
    """Clear stored join requests once a user joins, leaves after joining, or is banned."""
    if not event.chat or not event.new_chat_member or not event.new_chat_member.user:
        return

    old_status = str(getattr(getattr(event.old_chat_member, "status", ""), "value", getattr(event.old_chat_member, "status", ""))).lower()
    new_status = str(getattr(getattr(event.new_chat_member, "status", ""), "value", getattr(event.new_chat_member, "status", ""))).lower()

    if new_status in ("creator", "administrator", "member", "kicked") or old_status in (
        "creator",
        "administrator",
        "member",
    ):
        candidates = await _matching_channel_ids(event.chat.id, getattr(event.chat, "username", None))
        if not candidates:
            candidates = _chat_candidate_ids(event.chat.id, getattr(event.chat, "username", None))
        await remove_join_request(settings.db_path, event.new_chat_member.user.id, candidates)
