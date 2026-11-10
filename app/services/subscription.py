"""Sponsor channel subscription checking service."""

import logging
from typing import Any, Dict, List, Tuple
from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.db import get_channels

logger = logging.getLogger(__name__)


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
        try:
            member = await bot.get_chat_member(chat_id=ch["channel_id"], user_id=user_id)
            if member.status in ("left", "kicked"):
                unsubscribed.append(ch)
        except Exception as e:
            logger.warning(
                "Could not verify chat member for user %s in channel %s: %s",
                user_id,
                ch["channel_id"],
                e,
            )
            # If bot is not in the channel or cannot verify, do not block user
            pass

    return (len(unsubscribed) == 0), unsubscribed


def get_subscription_keyboard(unsubscribed_channels: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    """Build inline keyboard with links to join unsubscribed channels and a verify button."""
    keyboard: List[List[InlineKeyboardButton]] = []
    for idx, ch in enumerate(unsubscribed_channels, start=1):
        title = ch.get("title") or f"Homiy kanal #{idx}"
        url = ch.get("url") or f"https://t.me/{str(ch.get('channel_id')).lstrip('@')}"
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
