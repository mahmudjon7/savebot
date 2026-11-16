"""Self-advertising: re-post the admin's last broadcast ad to ONE chosen sponsor chat.

Flow: the admin sends an ad through "Reklama tarqatish" (video, photo, GIF or text).
The bot broadcasts it to all users and remembers that message. If auto-promo is
enabled, a small background loop copies the same ad to the chosen sponsor
channel/group every N minutes (the admin picks the chat and interval in the menu).
"""

import asyncio
import html
import logging
import time
from typing import Any, Dict, List, Optional

from aiogram import Bot
from aiogram.types import Message

from app.db import get_autopromo, update_autopromo

logger = logging.getLogger("clipgrab.autopromo")

# (minutes, button label)
INTERVAL_CHOICES: List[tuple] = [
    (5, "5 daqiqa"),
    (15, "15 daqiqa"),
    (30, "30 daqiqa"),
    (60, "1 soat"),
    (180, "3 soat"),
    (360, "6 soat"),
    (720, "12 soat"),
    (1440, "24 soat"),
]
ALLOWED_INTERVALS = {m for m, _ in INTERVAL_CHOICES}

# (hours, button label) - how long the auto-promo keeps running before it stops itself
DURATION_CHOICES: List[tuple] = [
    (1, "1 soat"),
    (2, "2 soat"),
    (3, "3 soat"),
    (5, "5 soat"),
    (8, "8 soat"),
    (10, "10 soat"),
    (12, "12 soat"),
    (24, "24 soat"),
]
ALLOWED_DURATIONS = {h for h, _ in DURATION_CHOICES}

TICK_SECONDS = 30


def describe_message(message: Message) -> str:
    """Short Uzbek label for the kind of ad message (for the admin menu)."""
    if getattr(message, "video", None) or getattr(message, "video_note", None):
        return "video"
    if getattr(message, "animation", None):
        return "GIF"
    if getattr(message, "photo", None):
        return "rasm"
    if getattr(message, "text", None):
        return "matn"
    return "xabar"


def is_due(cfg: Dict[str, Any], now: Optional[float] = None) -> bool:
    """True when promo is enabled, has an ad, a target chat and the interval has elapsed."""
    if not cfg.get("enabled") or not cfg.get("chat_id") or not cfg.get("src_message_id"):
        return False
    now = time.time() if now is None else now
    if cfg.get("end_ts") and now >= int(cfg["end_ts"]):
        return False
    return now - int(cfg.get("last_sent_ts") or 0) >= int(cfg["interval_min"]) * 60


async def start_promo(db_path: str) -> None:
    """Enable auto-promo now: first post goes out right away, it stops after duration_h hours."""
    cfg = await get_autopromo(db_path)
    await update_autopromo(
        db_path,
        enabled=True,
        last_sent_ts=0,
        end_ts=int(time.time()) + int(cfg["duration_h"]) * 3600,
        last_error=None,
    )


async def expire_if_needed(bot: Bot, db_path: str, now: Optional[float] = None) -> bool:
    """Stop auto-promo once its duration is over and tell the admins. Returns True if stopped."""
    cfg = await get_autopromo(db_path)
    now = time.time() if now is None else now
    if not cfg["enabled"] or not cfg["end_ts"] or now < cfg["end_ts"]:
        return False
    await update_autopromo(db_path, enabled=False, end_ts=0)
    from app import texts
    from app.config import settings

    note = texts.PROMO_FINISHED.format(chat=html.escape(cfg["chat_title"] or str(cfg["chat_id"])))
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, note, parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.debug("Could not notify admin %s: %s", admin_id, e)
    return True


async def send_promo(bot: Bot, cfg: Dict[str, Any]) -> None:
    """Copy the saved ad message into the configured chat (no 'forwarded from' header)."""
    chat_id: Any = cfg["chat_id"]
    try:
        chat_id = int(chat_id)
    except (TypeError, ValueError):
        pass
    await bot.copy_message(
        chat_id=chat_id,
        from_chat_id=int(cfg["src_chat_id"]),
        message_id=int(cfg["src_message_id"]),
    )


async def run_promo_once(bot: Bot, db_path: str, force: bool = False) -> Optional[str]:
    """Send one promo if due (or forced). Returns an error string, or None on success/skip."""
    if not force and await expire_if_needed(bot, db_path):
        return None
    cfg = await get_autopromo(db_path)
    if force:
        if not cfg["chat_id"]:
            return "Chat tanlanmagan"
        if not cfg["src_message_id"]:
            return "Reklama hali yuborilmagan"
    elif not is_due(cfg):
        return None
    # Move the clock first so a failing chat is retried only after the next interval.
    await update_autopromo(db_path, last_sent_ts=int(time.time()))
    try:
        await send_promo(bot, cfg)
    except Exception as e:  # noqa: BLE001 - surface any Telegram error to the admin menu
        logger.warning("Auto-promo failed for chat %s: %s", cfg["chat_id"], e)
        err = str(e)[:200]
        await update_autopromo(db_path, last_error=err)
        return err
    await update_autopromo(db_path, last_error=None)
    return None


async def run_autopromo_scheduler(bot: Bot, db_path: str) -> None:
    """Background loop: check settings every TICK_SECONDS and post when due."""
    logger.info("Auto-promo scheduler started.")
    while True:
        try:
            await run_promo_once(bot, db_path)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Auto-promo tick crashed")
        await asyncio.sleep(TICK_SECONDS)
