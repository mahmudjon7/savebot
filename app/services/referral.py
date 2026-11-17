"""Referral (taklif) system and video branding helpers.

Counting rules, so the numbers stay correct:
- a referral is recorded only when a brand-new user (never seen by the bot) opens the bot
  through someone else's link, and the inviter is a real bot user;
- one record per invitee, ever (database primary key), so nobody is counted twice;
- it becomes "confirmed" (and counts in the TOP list) only once the invitee has passed the
  sponsor-channel subscription check, and the inviter is told exactly once.
"""

import html
import logging
from typing import Optional, Tuple
from urllib.parse import quote

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.db import confirm_referral, get_leaderboard, get_referral_counts
from app.services.contest import is_contest_active

logger = logging.getLogger(__name__)

TOP_SIZE = 10
_MEDALS = ["🥇", "🥈", "🥉"]


def parse_ref_payload(args: Optional[str]) -> Optional[int]:
    """Extract the inviter's user ID from a '/start ref_<id>' payload."""
    if not args or not args.startswith("ref_"):
        return None
    raw = args[4:]
    return int(raw) if raw.isdigit() and 0 < len(raw) <= 15 else None


def make_ref_link(bot_username: str, user_id: int) -> str:
    return f"https://t.me/{bot_username}?start=ref_{user_id}"


def share_url(link: str) -> str:
    """Telegram share-dialog URL that pre-fills the invitation text and the user's own link."""
    return f"https://t.me/share/url?url={quote(link, safe='')}&text={quote(texts.SHARE_TEXT, safe='')}"


async def _bot_username(bot: Bot) -> str:
    me = await bot.me()
    return me.username or ""


async def video_branding(bot: Bot, user_id: int, platform: Optional[str]) -> Tuple[str, Optional[InlineKeyboardMarkup]]:
    """Caption with the bot name plus a 'share with a friend' button carrying the sender's referral link."""
    label = html.escape(platform or "Video")
    username = await _bot_username(bot)
    if not username:
        return label, None
    caption = f"{label}\n\n{texts.VIDEO_BRAND.format(bot=username)}"
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.REF_BTN_SHARE, url=share_url(make_ref_link(username, user_id)))]
        ]
    )
    return caption, markup


def referral_menu_keyboard(contest_active: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=texts.REF_BTN_INVITE, callback_data="ref:me")],
        [InlineKeyboardButton(text=texts.REF_BTN_TOP, callback_data="ref:top")],
    ]
    if contest_active:
        rows.insert(0, [InlineKeyboardButton(text=texts.CT_BTN_OPEN, callback_data="ct:me")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def confirm_and_notify(bot: Bot, db_path: str, invitee_id: int) -> bool:
    """Confirm the invitee's pending referral and tell the inviter. True only on the confirming call."""
    inviter_id = await confirm_referral(db_path, invitee_id)
    if inviter_id is None:
        return False
    counts = await get_referral_counts(db_path, inviter_id)
    try:
        await bot.send_message(
            inviter_id,
            texts.REF_NEW_FRIEND.format(count=counts["confirmed"]),
            parse_mode="HTML",
        )
    except Exception as e:  # noqa: BLE001 - inviter may have blocked the bot
        logger.debug("Could not notify inviter %s: %s", inviter_id, e)
    return True


def _display_name(username: Optional[str], user_id: int) -> str:
    if username:
        return "@" + html.escape(username)
    return texts.REF_ANON_NAME.format(tail=str(user_id)[-4:])


display_name = _display_name


async def render_my_referrals(bot: Bot, db_path: str, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    """Personal invite link, counts and rank, with a share button."""
    username = await _bot_username(bot)
    link = make_ref_link(username, user_id)
    counts = await get_referral_counts(db_path, user_id)
    board = await get_leaderboard(db_path)
    mine = next((row for row in board if row["user_id"] == user_id), None)
    text = texts.REF_MY_INFO.format(
        link=link,
        confirmed=counts["confirmed"],
        pending=counts["pending"],
        rank=mine["rank"] if mine else texts.REF_RANK_NONE,
    )
    rows = [
        [InlineKeyboardButton(text=texts.REF_BTN_SHARE, url=share_url(link))],
        [InlineKeyboardButton(text=texts.REF_BTN_TOP, callback_data="ref:top")],
    ]
    if await is_contest_active(db_path):
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_OPEN, callback_data="ct:me")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def render_top(db_path: str, user_id: int) -> str:
    """TOP inviters list plus the viewer's own position."""
    board = await get_leaderboard(db_path)
    if not board:
        return texts.REF_TOP_TITLE.format(rows=texts.REF_TOP_EMPTY)
    rows = []
    for row in board[:TOP_SIZE]:
        medal = _MEDALS[row["rank"] - 1] if row["rank"] <= len(_MEDALS) else f"{row['rank']}."
        rows.append(
            texts.REF_TOP_ROW.format(
                medal=medal, name=_display_name(row["username"], row["user_id"]), count=row["count"]
            )
        )
    text = texts.REF_TOP_TITLE.format(rows="\n".join(rows))
    mine = next((row for row in board if row["user_id"] == user_id), None)
    if mine:
        text += texts.REF_TOP_YOU.format(rank=mine["rank"], count=mine["count"])
    else:
        text += texts.REF_TOP_YOU_NONE
    return text
