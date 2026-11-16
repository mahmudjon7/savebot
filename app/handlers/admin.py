"""Admin panel handlers with broadcast and sponsor channel management."""

import asyncio
import html
import logging
import subprocess
import sys
import time
from typing import List, Optional, Tuple, Union
from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    MessageOriginChannel,
)
import yt_dlp

from app import texts
from app.config import settings
from app.db import (
    add_channel,
    get_all_user_ids,
    get_autopromo,
    get_channels,
    get_stats_24h,
    remove_channel,
    remove_channel_by_id,
    remove_user,
    update_autopromo,
)
from app.services.autopromo import (
    ALLOWED_DURATIONS,
    ALLOWED_INTERVALS,
    DURATION_CHOICES,
    INTERVAL_CHOICES,
    describe_message,
    run_promo_once,
    start_promo,
)
from app.services.subscription import normalize_channel_url, parse_channel_identifier

logger = logging.getLogger(__name__)
router = Router(name="admin")


class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_channel = State()


def is_admin(user_id: int) -> bool:
    """Check if the given Telegram user ID is in admin_ids."""
    return user_id in settings.admin_ids


def get_admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Main admin panel keyboard."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=texts.ADMIN_BTN_STATS, callback_data="admin:stats"),
                InlineKeyboardButton(text=texts.ADMIN_BTN_BROADCAST, callback_data="admin:broadcast"),
            ],
            [
                InlineKeyboardButton(text=texts.ADMIN_BTN_CHANNELS, callback_data="admin:channels"),
                InlineKeyboardButton(text=texts.ADMIN_BTN_UPDATE_YTDLP, callback_data="admin:update_ytdlp"),
            ],
            [InlineKeyboardButton(text=texts.ADMIN_BTN_PROMO, callback_data="promo:menu")],
        ]
    )


@router.message(Command("cancel"))
async def handle_cancel(message: Message, state: FSMContext) -> None:
    """Cancel any active admin state."""
    if not message.from_user or not is_admin(message.from_user.id):
        return
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.reply("❌ Amal bekor qilindi.", reply_markup=get_admin_menu_keyboard())


@router.message(Command("admin"))
async def handle_admin_command(message: Message, state: FSMContext) -> None:
    """Open the admin panel."""
    if not message.from_user or not is_admin(message.from_user.id):
        await message.reply(texts.ADMIN_ONLY)
        return
    await state.clear()
    await message.reply(texts.ADMIN_PANEL_TITLE, reply_markup=get_admin_menu_keyboard(), parse_mode="HTML")


@router.callback_query(F.data == "admin:menu")
async def callback_admin_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Return to admin main menu."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    if callback.message:
        await callback.message.edit_text(
            texts.ADMIN_PANEL_TITLE,
            reply_markup=get_admin_menu_keyboard(),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def callback_stats(callback: CallbackQuery) -> None:
    """Show 24-hour statistics."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    stats = await get_stats_24h(settings.db_path)
    text = texts.STATS_TEMPLATE.format(
        total_users=stats["total_users"],
        total_channels=stats["total_channels"],
        total_downloads=stats["total_downloads"],
        cache_hits=stats["cache_hits"],
        hit_rate=stats["hit_rate"],
        failures=stats["failures"],
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:menu")]]
    )
    if callback.message:
        await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


# ---------------- BROADCAST (REKLAMA) ----------------

@router.callback_query(F.data == "admin:broadcast")
async def callback_broadcast_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin to send the broadcast message."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_broadcast)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:menu")]]
    )
    if callback.message:
        await callback.message.edit_text(texts.BROADCAST_START_PROMPT, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.waiting_for_broadcast)
async def process_broadcast_message(message: Message, state: FSMContext) -> None:
    """Remember the ad the admin sent and ask where to send it (users or channel auto-promo)."""
    if not message.from_user or not is_admin(message.from_user.id):
        return

    await state.clear()
    kind = describe_message(message)
    await update_autopromo(
        settings.db_path,
        src_chat_id=message.chat.id,
        src_message_id=message.message_id,
        src_kind=kind,
        last_error=None,
    )
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.AD_BTN_USERS, callback_data="bc:users")],
            [InlineKeyboardButton(text=texts.AD_BTN_CHANNEL, callback_data="promo:chat:w")],
            [InlineKeyboardButton(text=texts.AD_BTN_CANCEL, callback_data="admin:menu")],
        ]
    )
    await message.reply(texts.AD_RECEIVED.format(kind=kind), reply_markup=keyboard, parse_mode="HTML")


@router.callback_query(F.data == "bc:users")
async def callback_broadcast_to_users(callback: CallbackQuery) -> None:
    """Send the saved ad to every user in the database."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    cfg = await get_autopromo(settings.db_path)
    if not cfg["src_message_id"]:
        await callback.answer(texts.PROMO_NEED_AD, show_alert=True)
        return
    await callback.answer()
    status_msg = callback.message
    await status_msg.edit_text(texts.BROADCAST_PROGRESS)

    bot = callback.bot
    src_chat, src_msg = int(cfg["src_chat_id"]), int(cfg["src_message_id"])
    user_ids = await get_all_user_ids(settings.db_path)
    total = len(user_ids)
    sent = 0
    blocked = 0

    for uid in user_ids:
        try:
            await bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
            sent += 1
            await asyncio.sleep(0.04)  # ~25 messages/second to prevent flood limits
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.copy_message(chat_id=uid, from_chat_id=src_chat, message_id=src_msg)
                sent += 1
            except Exception:
                pass
        except (TelegramForbiddenError, TelegramBadRequest):
            # User blocked the bot or deleted account; remove from DB to keep database lean!
            blocked += 1
            await remove_user(settings.db_path, uid)
        except Exception as e:
            logger.debug("Failed sending broadcast to %s: %s", uid, e)

    await status_msg.edit_text(
        texts.BROADCAST_FINISHED.format(total=total, sent=sent, blocked=blocked),
        reply_markup=get_admin_menu_keyboard(),
        parse_mode="HTML",
    )


# ---------------- SPONSOR CHANNELS (HOMIY KANALLAR) ----------------

async def render_channels_menu(message: Message, is_edit: bool = True) -> None:
    """Display all sponsor channels with delete buttons and an add button."""
    channels = await get_channels(settings.db_path)
    keyboard_rows: List[List[InlineKeyboardButton]] = []

    if not channels:
        text = texts.CHANNELS_EMPTY
    else:
        text = texts.CHANNELS_TITLE
        for ch in channels:
            ch_title = ch["title"] or ch["channel_id"]
            del_key = ch["id"] if ch.get("id") is not None else ch["channel_id"]
            valid_url = normalize_channel_url(ch.get("url"), ch.get("channel_id"))
            first_btn = (
                InlineKeyboardButton(text=f"📢 {ch_title}", url=valid_url)
                if valid_url
                else InlineKeyboardButton(text=f"⚠️ {ch_title}", callback_data="ch:bad_url")
            )
            keyboard_rows.append([
                first_btn,
                InlineKeyboardButton(text="❌ O'chirish", callback_data=f"ch:del:{del_key}"),
            ])

    keyboard_rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_ADD_CHANNEL, callback_data="ch:add")])
    keyboard_rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:menu")])

    markup = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    if is_edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.reply(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "admin:channels")
async def callback_channels_list(callback: CallbackQuery, state: FSMContext) -> None:
    """Show sponsor channels list and clear any pending channel-add state."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    if callback.message:
        await render_channels_menu(callback.message, is_edit=True)
    await callback.answer()


@router.callback_query(F.data == "ch:bad_url")
async def callback_channel_bad_url(callback: CallbackQuery) -> None:
    """Inform admin about a malformed stored sponsor URL."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await callback.answer(texts.CHANNEL_INVALID_URL_ALERT, show_alert=True)


@router.callback_query(F.data.startswith("ch:del:"))
async def callback_channel_delete(callback: CallbackQuery) -> None:
    """Delete a sponsor channel by DB row ID or channel_id."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    target = callback.data.split("ch:del:", 1)[1]
    if target.isdigit():
        removed_cid = await remove_channel_by_id(settings.db_path, int(target))
        display_id = removed_cid or target
    else:
        await remove_channel(settings.db_path, target)
        display_id = target

    await callback.answer(
        texts.CHANNEL_DELETED_SUCCESS.format(channel_id=display_id).replace("<code>", "").replace("</code>", ""),
        show_alert=True,
    )
    if callback.message:
        await render_channels_menu(callback.message, is_edit=True)


@router.callback_query(F.data == "ch:add")
async def callback_channel_add_start(callback: CallbackQuery, state: FSMContext) -> None:
    """Prompt admin for channel details."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    await state.set_state(AdminStates.waiting_for_channel)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:channels")]]
    )
    if callback.message:
        await callback.message.edit_text(texts.CHANNEL_ADD_PROMPT, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


def _extract_channel_input(
    message: Message,
) -> Tuple[Optional[Union[int, str]], Optional[str], Optional[str], Optional[str]]:
    """
    Parse channel input from a forwarded channel post or pipe-separated/single text.
    Returns (lookup_id, custom_title, custom_url, error_reply_html).
    """
    origin = getattr(message, "forward_origin", None)
    fwd_chat = origin.chat if isinstance(origin, MessageOriginChannel) else getattr(message, "forward_from_chat", None)
    if fwd_chat is not None:
        return fwd_chat.id, None, None, None
    if origin is not None:
        return None, None, None, texts.CHANNEL_ADD_NOT_CHANNEL

    if not message.text:
        return None, None, None, texts.CHANNEL_ADD_FAILED

    text = message.text.strip()
    custom_title: Optional[str] = None
    custom_url: Optional[str] = None
    if "|" in text:
        parts = [p.strip() for p in text.split("|")]
        raw_id = parts[0]
        custom_title = parts[1] if len(parts) >= 2 and parts[1] else None
        custom_url = parts[2] if len(parts) >= 3 and parts[2] else None
    else:
        raw_id = text

    lookup_id, invite_only = parse_channel_identifier(raw_id)
    if invite_only:
        return (
            None,
            None,
            None,
            texts.CHANNEL_ADD_INVITE_LINK_ONLY.format(invite_url=html.escape(invite_only)),
        )
    if lookup_id is None:
        return None, None, None, texts.CHANNEL_ADD_FAILED

    if custom_url:
        normalized_custom = normalize_channel_url(custom_url)
        if not normalized_custom:
            return None, None, None, texts.CHANNEL_ADD_INVALID_URL
        custom_url = normalized_custom

    return lookup_id, custom_title, custom_url, None


async def _cleanup_legacy_channel_aliases(
    db_path: str,
    canonical_id: str,
    username: Optional[str],
) -> None:
    """Remove duplicate legacy channel entries (e.g., @username or URL) for the same chat."""
    if not username:
        return
    target_uname = f"@{username.lower()}"
    for row in await get_channels(db_path):
        existing_cid = str(row["channel_id"])
        if existing_cid == canonical_id:
            continue
        parsed, _ = parse_channel_identifier(existing_cid)
        if isinstance(parsed, str) and parsed.lower() == target_uname:
            await remove_channel(db_path, existing_cid)


@router.message(AdminStates.waiting_for_channel)
async def process_channel_add(message: Message, state: FSMContext) -> None:
    """Process channel addition from admin input and verify bot admin access."""
    if not message.from_user or not is_admin(message.from_user.id):
        return

    lookup_id, custom_title, custom_url, parse_err = _extract_channel_input(message)
    if parse_err or lookup_id is None:
        await message.reply(parse_err or texts.CHANNEL_ADD_FAILED, parse_mode="HTML")
        return

    try:
        chat = await message.bot.get_chat(lookup_id)
    except Exception as e:
        logger.warning("Could not fetch sponsor channel %s: %s", lookup_id, e)
        await message.reply(texts.CHANNEL_ADD_FAILED, parse_mode="HTML")
        return

    if getattr(chat, "type", None) not in ("channel", "supergroup", "group"):
        await message.reply(texts.CHANNEL_ADD_NOT_CHANNEL)
        return

    try:
        bot_member = await message.bot.get_chat_member(chat_id=chat.id, user_id=message.bot.id)
        bot_status = str(getattr(getattr(bot_member, "status", ""), "value", getattr(bot_member, "status", ""))).lower()
    except Exception as e:
        logger.warning("Bot cannot check membership in channel %s: %s", chat.id, e)
        await message.reply(texts.CHANNEL_ADD_NOT_ADMIN, parse_mode="HTML")
        return

    if bot_status not in ("administrator", "creator"):
        await message.reply(texts.CHANNEL_ADD_NOT_ADMIN, parse_mode="HTML")
        return

    title = custom_title or chat.title or (f"@{chat.username}" if chat.username else str(chat.id))
    url: Optional[str] = custom_url
    if not url:
        if chat.username:
            url = f"https://t.me/{chat.username}"
        else:
            url = normalize_channel_url(getattr(chat, "invite_link", None))
            if not url:
                try:
                    exported = await message.bot.export_chat_invite_link(chat.id)
                    url = normalize_channel_url(exported)
                except Exception as e:
                    logger.warning("Could not export invite link for private channel %s: %s", chat.id, e)

    if not url:
        await message.reply(
            texts.CHANNEL_ADD_NO_INVITE_LINK.format(
                channel_id=chat.id,
                title=html.escape(title),
            ),
            parse_mode="HTML",
        )
        return

    canonical_id = str(chat.id)
    await _cleanup_legacy_channel_aliases(settings.db_path, canonical_id, getattr(chat, "username", None))
    success = await add_channel(settings.db_path, channel_id=canonical_id, title=title, url=url)
    await state.clear()

    if success:
        await message.reply(
            texts.CHANNEL_ADDED_SUCCESS.format(
                title=html.escape(title),
                channel_id=html.escape(canonical_id),
                url=html.escape(url),
            ),
            reply_markup=get_admin_menu_keyboard(),
            parse_mode="HTML",
        )
    else:
        await message.reply(texts.CHANNEL_ADD_FAILED, reply_markup=get_admin_menu_keyboard(), parse_mode="HTML")


# ---------------- AUTO-PROMO (AVTO-REKLAMA) ----------------

def _interval_label(minutes: int) -> str:
    for value, label in INTERVAL_CHOICES:
        if value == minutes:
            return label
    return f"{minutes} daqiqa"


def _duration_label(hours: int) -> str:
    for value, label in DURATION_CHOICES:
        if value == hours:
            return label
    return f"{hours} soat"


def _left_label(seconds: int) -> str:
    minutes = max(int(seconds) // 60, 0)
    hours, mins = divmod(minutes, 60)
    return f"{hours} soat {mins} daqiqa" if hours else f"{mins} daqiqa"


async def render_promo_menu(message: Message, is_edit: bool = True) -> None:
    """Show auto-promo status and its control buttons."""
    cfg = await get_autopromo(settings.db_path)
    error_line = (
        texts.PROMO_ERROR_LINE.format(error=html.escape(cfg["last_error"])) if cfg["last_error"] else ""
    )
    remaining = ""
    if cfg["enabled"] and cfg["end_ts"]:
        remaining = texts.PROMO_REMAINING.format(left=_left_label(cfg["end_ts"] - time.time()))
    text = texts.PROMO_MENU.format(
        status="🟢 Yoniq" if cfg["enabled"] else "🔴 O'chiq",
        chat=html.escape(cfg["chat_title"] or "tanlanmagan"),
        interval=_interval_label(cfg["interval_min"]),
        duration=_duration_label(cfg["duration_h"]),
        remaining=remaining,
        ad=(
            texts.PROMO_AD_SAVED.format(kind=cfg["src_kind"] or "xabar")
            if cfg["src_message_id"]
            else texts.PROMO_AD_NONE
        ),
        error_line=error_line,
    )
    toggle_text = texts.PROMO_BTN_DISABLE if cfg["enabled"] else texts.PROMO_BTN_ENABLE
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=toggle_text, callback_data="promo:toggle")],
            [
                InlineKeyboardButton(text=texts.PROMO_BTN_CHAT, callback_data="promo:chat"),
                InlineKeyboardButton(text=texts.PROMO_BTN_INTERVAL, callback_data="promo:interval"),
            ],
            [InlineKeyboardButton(text=texts.PROMO_BTN_DURATION, callback_data="promo:duration")],
            [InlineKeyboardButton(text=texts.PROMO_BTN_NOW, callback_data="promo:now")],
            [InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:menu")],
        ]
    )
    if is_edit:
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.reply(text, reply_markup=markup, parse_mode="HTML")


def _is_wizard(data: str) -> bool:
    """Callback data ending in ':w' means the admin is in the step-by-step setup after sending an ad."""
    return data.endswith(":w")


async def _show_chat_picker(message: Message, wizard: bool) -> None:
    channels = await get_channels(settings.db_path)
    suffix = ":w" if wizard else ""
    rows: List[List[InlineKeyboardButton]] = [
        [
            InlineKeyboardButton(
                text=f"📢 {ch['title'] or ch['channel_id']}",
                callback_data=f"promo:setchat:{ch['id']}{suffix}",
            )
        ]
        for ch in channels
    ]
    back = "admin:menu" if wizard else "promo:menu"
    rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data=back)])
    await message.edit_text(
        texts.PROMO_CHOOSE_CHAT if channels else texts.PROMO_NO_CHANNELS,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


async def _show_interval_picker(message: Message, wizard: bool) -> None:
    suffix = ":w" if wizard else ""
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"promo:setint:{minutes}{suffix}")
        for minutes, label in INTERVAL_CHOICES
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="promo:menu")])
    await message.edit_text(
        texts.PROMO_CHOOSE_INTERVAL, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


async def _show_duration_picker(message: Message, wizard: bool) -> None:
    suffix = ":w" if wizard else ""
    buttons = [
        InlineKeyboardButton(text=label, callback_data=f"promo:setdur:{hours}{suffix}")
        for hours, label in DURATION_CHOICES
    ]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="promo:menu")])
    await message.edit_text(
        texts.PROMO_CHOOSE_DURATION, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML"
    )


@router.callback_query(F.data == "promo:menu")
async def callback_promo_menu(callback: CallbackQuery, state: FSMContext) -> None:
    """Open the auto-promo menu."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    await state.clear()
    if callback.message:
        await render_promo_menu(callback.message, is_edit=True)
    await callback.answer()


@router.callback_query(F.data == "promo:toggle")
async def callback_promo_toggle(callback: CallbackQuery) -> None:
    """Enable or disable auto-promo."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    cfg = await get_autopromo(settings.db_path)
    if cfg["enabled"]:
        await update_autopromo(settings.db_path, enabled=False, end_ts=0)
    else:
        if not cfg["chat_id"]:
            await callback.answer(texts.PROMO_NEED_CHAT, show_alert=True)
            return
        if not cfg["src_message_id"]:
            await callback.answer(texts.PROMO_NEED_AD, show_alert=True)
            return
        await start_promo(settings.db_path)
    if callback.message:
        await render_promo_menu(callback.message, is_edit=True)
    await callback.answer()


@router.callback_query(F.data.in_({"promo:chat", "promo:chat:w"}))
async def callback_promo_chat(callback: CallbackQuery) -> None:
    """List sponsor channels/groups to choose the ad target from."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    if callback.message:
        await _show_chat_picker(callback.message, _is_wizard(callback.data))
    await callback.answer()


@router.callback_query(F.data.startswith("promo:setchat:"))
async def callback_promo_set_chat(callback: CallbackQuery) -> None:
    """Save the chosen sponsor channel as the single ad target."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    wizard = _is_wizard(callback.data)
    raw = callback.data.split("promo:setchat:", 1)[1].removesuffix(":w")
    channels = await get_channels(settings.db_path)
    chosen = next((ch for ch in channels if str(ch["id"]) == raw), None)
    if not chosen:
        await callback.answer(texts.CHANNEL_ADD_FAILED.split("\n")[0], show_alert=True)
        return
    await update_autopromo(
        settings.db_path,
        chat_id=str(chosen["channel_id"]),
        chat_title=chosen["title"] or str(chosen["channel_id"]),
        last_error=None,
    )
    if callback.message:
        if wizard:
            await _show_interval_picker(callback.message, True)
        else:
            await render_promo_menu(callback.message, is_edit=True)
    await callback.answer()


@router.callback_query(F.data.in_({"promo:interval", "promo:interval:w"}))
async def callback_promo_interval(callback: CallbackQuery) -> None:
    """Show interval choices."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    if callback.message:
        await _show_interval_picker(callback.message, _is_wizard(callback.data))
    await callback.answer()


@router.callback_query(F.data.startswith("promo:setint:"))
async def callback_promo_set_interval(callback: CallbackQuery) -> None:
    """Save the chosen interval."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    wizard = _is_wizard(callback.data)
    raw = callback.data.split("promo:setint:", 1)[1].removesuffix(":w")
    if not raw.isdigit() or int(raw) not in ALLOWED_INTERVALS:
        await callback.answer("Noto'g'ri interval", show_alert=True)
        return
    await update_autopromo(settings.db_path, interval_min=int(raw))
    if callback.message:
        if wizard:
            await _show_duration_picker(callback.message, True)
        else:
            await render_promo_menu(callback.message, is_edit=True)
    await callback.answer()


@router.callback_query(F.data.in_({"promo:duration", "promo:duration:w"}))
async def callback_promo_duration(callback: CallbackQuery) -> None:
    """Show duration (hours) choices."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    if callback.message:
        await _show_duration_picker(callback.message, _is_wizard(callback.data))
    await callback.answer()


@router.callback_query(F.data.startswith("promo:setdur:"))
async def callback_promo_set_duration(callback: CallbackQuery) -> None:
    """Save the duration; in the setup wizard this also starts the auto-promo."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    wizard = _is_wizard(callback.data)
    raw = callback.data.split("promo:setdur:", 1)[1].removesuffix(":w")
    if not raw.isdigit() or int(raw) not in ALLOWED_DURATIONS:
        await callback.answer("Noto'g'ri davomiylik", show_alert=True)
        return
    hours = int(raw)
    await update_autopromo(settings.db_path, duration_h=hours)
    toast = None
    if wizard:
        await start_promo(settings.db_path)
        toast = texts.PROMO_STARTED_TOAST
    else:
        cfg = await get_autopromo(settings.db_path)
        if cfg["enabled"]:  # a running promo gets the new duration counted from now
            await update_autopromo(settings.db_path, end_ts=int(time.time()) + hours * 3600)
    if callback.message:
        await render_promo_menu(callback.message, is_edit=True)
    await callback.answer(toast)


@router.callback_query(F.data == "promo:now")
async def callback_promo_now(callback: CallbackQuery) -> None:
    """Send one ad right now to the chosen chat (test)."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return
    cfg = await get_autopromo(settings.db_path)
    if not cfg["chat_id"]:
        await callback.answer(texts.PROMO_NEED_CHAT, show_alert=True)
        return
    if not cfg["src_message_id"]:
        await callback.answer(texts.PROMO_NEED_AD, show_alert=True)
        return
    await callback.answer("⏳")
    error = await run_promo_once(callback.bot, settings.db_path, force=True)
    if callback.message:
        await callback.message.reply(
            texts.PROMO_SENT_FAIL.format(error=html.escape(error)) if error else texts.PROMO_SENT_OK,
            parse_mode="HTML",
        )
        await render_promo_menu(callback.message, is_edit=True)


# ---------------- UPDATE YT-DLP ----------------

def _run_pip_update() -> str:
    """Run pip install -U yt-dlp synchronously."""
    cmd = [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return res.stdout


@router.callback_query(F.data == "admin:update_ytdlp")
async def callback_update_ytdlp(callback: CallbackQuery) -> None:
    """Update yt-dlp from admin callback."""
    if not callback.from_user or not is_admin(callback.from_user.id):
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return

    status_msg = await callback.message.reply(texts.ADMIN_UPDATE_STARTED)
    await callback.answer()
    try:
        await asyncio.to_thread(_run_pip_update)
        import importlib
        importlib.reload(yt_dlp)
        version = getattr(yt_dlp, "__version__", getattr(yt_dlp.version, "__version__", "unknown"))

        await status_msg.edit_text(
            texts.ADMIN_UPDATE_SUCCESS.format(version=version),
            reply_markup=get_admin_menu_keyboard(),
            parse_mode="HTML",
        )
    except Exception as e:
        logger.exception("yt-dlp update failed: %s", e)
        await status_msg.edit_text(
            texts.ADMIN_UPDATE_FAILED.format(error=str(e)),
            reply_markup=get_admin_menu_keyboard(),
            parse_mode="HTML",
        )
