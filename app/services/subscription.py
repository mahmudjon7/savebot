"""Sponsor channel subscription checking and normalization service."""

import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urlparse

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db import get_channels, has_join_request, remove_join_request

logger = logging.getLogger(__name__)

_TG_HOSTS = {"t.me", "telegram.me", "telegram.dog"}
_USERNAME_WITH_PREFIX_RE = re.compile(r"^[A-Za-z0-9_]{3,}$")
_BARE_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{2,}$")
_NUMERIC_ID_RE = re.compile(r"^-?\d+$")
_USER_NOT_FOUND_MARKERS = (
    "user not found",
    "user_id_invalid",
    "participant_id_invalid",
)


def parse_channel_identifier(
    raw: str,
) -> Tuple[Optional[Union[int, str]], Optional[str]]:
    """
    Normalize a raw channel input into a Telegram chat identifier.

    Returns (lookup_id, invite_only_url):
    - lookup_id is an int (for numeric chat IDs like -100123...) or '@username'.
    - invite_only_url is populated when the input is an invite link (t.me/+... or joinchat/...)
      which cannot be passed directly to Bot API getChat / getChatMember.
    """
    if not raw:
        return None, None

    cleaned = raw.strip()
    if not cleaned:
        return None, None

    if _NUMERIC_ID_RE.match(cleaned):
        return int(cleaned), None

    candidate_url = cleaned
    lower = cleaned.lower()
    if any(lower.startswith(f"{host}/") for host in _TG_HOSTS):
        candidate_url = f"https://{cleaned}"

    if candidate_url.lower().startswith(("http://", "https://")):
        parsed = urlparse(candidate_url)
        host = (parsed.hostname or "").lower()
        if host not in _TG_HOSTS:
            return None, None

        segments = [seg for seg in parsed.path.split("/") if seg]
        if not segments:
            return None, None

        first = segments[0]
        if first.startswith("+") or first.lower() == "joinchat":
            invite_url = f"https://t.me/{'/'.join(segments)}"
            return None, invite_url

        if first.lower() == "c" and len(segments) >= 2 and segments[1].isdigit():
            return int(f"-100{segments[1]}"), None

        if _USERNAME_WITH_PREFIX_RE.match(first):
            return f"@{first}", None

        return None, None

    if cleaned.startswith("@"):
        username = cleaned[1:]
        if _USERNAME_WITH_PREFIX_RE.match(username):
            return f"@{username}", None
        return None, None

    if _BARE_USERNAME_RE.match(cleaned):
        return f"@{cleaned}", None

    return None, None


def normalize_channel_url(
    raw_url: Optional[str],
    channel_id: Optional[str] = None,
) -> Optional[str]:
    """Validate and normalize a Telegram channel/invite URL for inline buttons."""

    def _validate(val: Optional[str]) -> Optional[str]:
        if not val:
            return None
        text = val.strip()
        if not text or any(ch.isspace() for ch in text):
            return None

        if text.startswith("@"):
            uname = text[1:]
            if _USERNAME_WITH_PREFIX_RE.match(uname):
                return f"https://t.me/{uname}"
            return None

        lower = text.lower()
        if any(lower.startswith(f"{host}/") for host in _TG_HOSTS):
            text = f"https://{text}"

        parsed = urlparse(text)
        scheme = parsed.scheme.lower()
        if scheme not in ("http", "https", "tg"):
            return None

        if scheme in ("http", "https"):
            if not parsed.netloc:
                return None
            host = (parsed.hostname or "").lower()
            if host in _TG_HOSTS:
                segments = [seg for seg in parsed.path.split("/") if seg]
                if not segments:
                    return None
                if segments[0].startswith("-") or segments[0].lower().startswith("http"):
                    return None
        return text

    valid = _validate(raw_url)
    if valid:
        return valid

    if channel_id:
        lookup_id, invite_url = parse_channel_identifier(str(channel_id))
        if invite_url:
            return invite_url
        if isinstance(lookup_id, str) and lookup_id.startswith("@"):
            return f"https://t.me/{lookup_id[1:]}"

    return None


def _is_member_status(member: Any) -> Tuple[bool, str]:
    """Interpret Telegram ChatMember status accurately across all member types."""
    raw_status = getattr(member, "status", "")
    status = str(getattr(raw_status, "value", raw_status)).lower()
    if status in ("creator", "administrator", "member"):
        return True, status
    if status == "restricted":
        return bool(getattr(member, "is_member", False)), status
    return False, status


async def _get_chat_member_with_retry(
    bot: Bot,
    chat_id: Union[int, str],
    user_id: int,
) -> Any:
    """Call bot.get_chat_member with brief backoff on flood control or transient network errors."""
    try:
        return await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except TelegramRetryAfter as e:
        await asyncio.sleep(min(float(e.retry_after), 3.0))
        return await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
    except (TelegramNetworkError, asyncio.TimeoutError):
        await asyncio.sleep(0.3)
        return await bot.get_chat_member(chat_id=chat_id, user_id=user_id)


async def check_user_subscriptions(
    bot: Bot,
    user_id: int,
    db_path: str,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Check if a user is subscribed to all active sponsor channels.
    Returns (is_all_subscribed, list_of_unsubscribed_channels).
    """
    channels = await get_channels(db_path)
    if not channels:
        return True, []

    unsubscribed: List[Dict[str, Any]] = []

    for ch in channels:
        raw_cid = str(ch["channel_id"])
        lookup_id, invite_only = parse_channel_identifier(raw_cid)
        if invite_only is not None or lookup_id is None:
            logger.error(
                "Invalid sponsor channel identifier in DB (%r) — skipping check until fixed.",
                raw_cid,
            )
            continue

        candidates = list(dict.fromkeys([raw_cid, str(lookup_id), str(lookup_id).lower()]))

        try:
            member = await _get_chat_member_with_retry(bot, lookup_id, user_id)
        except (TelegramBadRequest, TelegramForbiddenError) as e:
            err_lower = str(e).lower()
            if any(marker in err_lower for marker in _USER_NOT_FOUND_MARKERS):
                unsubscribed.append(ch)
            else:
                logger.error(
                    "Could not verify sponsor channel %s (bot may not be admin or chat missing): %s",
                    raw_cid,
                    e,
                )
            continue
        except Exception as e:
            logger.warning(
                "Could not verify chat member for user %s in channel %s: %s",
                user_id,
                raw_cid,
                e,
            )
            continue

        is_member, status = _is_member_status(member)
        if is_member:
            await remove_join_request(db_path, user_id, candidates)
            continue

        if status == "kicked":
            await remove_join_request(db_path, user_id, candidates)
            unsubscribed.append(ch)
            continue

        if await has_join_request(db_path, user_id, candidates):
            continue

        unsubscribed.append(ch)

    return (len(unsubscribed) == 0), unsubscribed


def get_subscription_keyboard(unsubscribed_channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Build inline keyboard with links to join unsubscribed channels and a verify button."""
    keyboard: List[List[InlineKeyboardButton]] = []
    for idx, ch in enumerate(unsubscribed_channels, start=1):
        title = ch.get("title") or f"Homiy kanal #{idx}"
        url = normalize_channel_url(ch.get("url"), ch.get("channel_id"))
        if url:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📢 {title}",
                    url=url,
                )
            ])

    keyboard.append([
        InlineKeyboardButton(
            text="✅ Obunani tekshirish",
            callback_data="sub:check",
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=keyboard)
