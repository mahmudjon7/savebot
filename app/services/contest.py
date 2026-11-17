"""Referral contest: join, standings, winner draw, and the end-of-contest scheduler.

Rules (kept simple so the result can be checked by hand):
- only users who pressed "join" take part;
- only *confirmed* referrals made between the contest start and end count (see referral rules);
- a participant qualifies with at least `min_invites` such referrals AND at least one video
  downloaded through the bot;
- place 1 goes to the qualified participant with the most invites (ties: who reached it earlier),
  the remaining places are drawn at random among the other qualified participants;
- the admin reviews the result (and can disqualify cheaters) before anyone is told.
"""

import asyncio
import logging
import random
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import aiosqlite
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app import texts
from app.config import settings
from app.db import get_all_user_ids, remove_user

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
START_PAYLOAD = "konkurs"
MIN_INVITES_CHOICES = (3, 5, 10, 15, 20, 30, 50)
DAYS_CHOICES = (3, 7, 10, 15, 20, 30)
WINNERS_CHOICES = (1, 2, 3, 5)
POST_INTERVAL_CHOICES = (1, 3, 6, 12, 24)  # hours between posts in the channel/group
EDIT_PAUSE = 1.2        # seconds between edits of old posts (Telegram per-chat limits)
MAX_TRACKED_POSTS = 400
TEXT_LIMIT = 3900       # body length (HTML) for a text post, footer included later
CAPTION_LIMIT = 900     # photo/video captions are limited to 1024 characters in total

# Uzbekistan is UTC+5 all year (no daylight saving), so a fixed offset is exact.
TZ = timezone(timedelta(hours=5))
UZ_MONTHS = (
    "yanvar", "fevral", "mart", "aprel", "may", "iyun",
    "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
)

_NOW = "strftime('%Y-%m-%d %H:%M:%f','now')"


def _connect(db_path: str) -> aiosqlite.Connection:
    return aiosqlite.connect(db_path, timeout=30)


async def get_contest(db_path: str) -> Dict[str, Any]:
    """Contest settings and state (the row is created on first use)."""
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest (id) VALUES (1);")
        await db.commit()
        async with db.execute(
            """
            SELECT status, days, min_invites, winners_count, started_at, ends_at,
                   CAST(COALESCE((julianday(ends_at) - julianday('now')) * 86400, 0) AS INTEGER),
                   (SELECT COUNT(*) FROM contest_members WHERE disqualified = 0)
            FROM contest WHERE id = 1;
            """
        ) as cur:
            row = await cur.fetchone()
    left = max(int(row[6]), 0)
    return {
        "status": row[0],
        "days": int(row[1]),
        "min_invites": int(row[2]),
        "winners_count": int(row[3]),
        "started_at": row[4],
        "ends_at": row[5],
        "seconds_left": left,
        "members": int(row[7]),
        "active": row[0] == "running" and left > 0,
    }


async def is_contest_active(db_path: str) -> bool:
    return (await get_contest(db_path))["active"]


async def update_settings(
    db_path: str,
    *,
    days: Optional[int] = None,
    min_invites: Optional[int] = None,
    winners_count: Optional[int] = None,
) -> None:
    """Change contest settings (days only matter at the next start)."""
    fields = {"days": days, "min_invites": min_invites, "winners_count": winners_count}
    fields = {k: int(v) for k, v in fields.items() if v is not None}
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest (id) VALUES (1);")
        await db.execute(f"UPDATE contest SET {assignments} WHERE id = 1;", list(fields.values()))
        await db.commit()


async def start_contest(db_path: str) -> None:
    """Start a fresh contest: clears earlier participants and winners."""
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest (id) VALUES (1);")
        await db.execute("DELETE FROM contest_members;")
        await db.execute("DELETE FROM contest_winners;")
        await db.execute("DELETE FROM contest_posts;")
        # The contest runs through the last calendar day and ends at 00:00 Tashkent time
        # (00:00 Tashkent = 19:00 UTC the day before), so "days left" drops by one at midnight.
        await db.execute(
            f"UPDATE contest SET status = 'running', started_at = {_NOW}, "
            "ends_at = strftime('%Y-%m-%d %H:%M:%f', date('now', '+5 hours', '+' || days || ' days'), '-5 hours') "
            "WHERE id = 1;"
        )
        await db.execute("INSERT OR IGNORE INTO contest_post (id) VALUES (1);")
        await db.execute(
            "UPDATE contest_post SET last_edit_date = ?, last_sent_ts = 0 WHERE id = 1;",
            (tashkent_today().isoformat(),),
        )
        await db.commit()


async def cancel_contest(db_path: str) -> None:
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest (id) VALUES (1);")
        await db.execute("UPDATE contest SET status = 'off' WHERE id = 1;")
        await db.commit()


async def join_contest(db_path: str, user_id: int) -> bool:
    """Add a participant. True only when newly joined (contest must be active)."""
    if not await is_contest_active(db_path):
        return False
    async with _connect(db_path) as db:
        cur = await db.execute("INSERT OR IGNORE INTO contest_members (user_id) VALUES (?);", (user_id,))
        await db.commit()
        return cur.rowcount == 1


async def get_member(db_path: str, user_id: int) -> Optional[Dict[str, Any]]:
    async with _connect(db_path) as db:
        async with db.execute(
            "SELECT disqualified FROM contest_members WHERE user_id = ?;", (user_id,)
        ) as cur:
            row = await cur.fetchone()
    return {"disqualified": bool(row[0])} if row else None


async def get_standings(db_path: str) -> List[Dict[str, Any]]:
    """Participants (not disqualified), best first, with in-contest confirmed invites and downloads."""
    sql = """
    SELECT m.user_id, u.username,
        (SELECT COUNT(*) FROM referrals r
          WHERE r.inviter_id = m.user_id AND r.status = 'confirmed'
            AND r.confirmed_at >= c.started_at AND r.confirmed_at <= c.ends_at) AS invites,
        (SELECT MAX(r.confirmed_at) FROM referrals r
          WHERE r.inviter_id = m.user_id AND r.status = 'confirmed'
            AND r.confirmed_at >= c.started_at AND r.confirmed_at <= c.ends_at) AS reached_at,
        (SELECT COUNT(*) FROM downloads d
          WHERE d.user_id = m.user_id AND d.status IN ('ok', 'cache_hit')) AS downloads,
        (SELECT COUNT(*) FROM referrals r
          WHERE r.inviter_id = m.user_id AND r.status = 'pending'
            AND r.created_at >= substr(c.started_at, 1, 19)) AS pending
    FROM contest_members m
    CROSS JOIN contest c
    LEFT JOIN users u ON u.user_id = m.user_id
    WHERE c.id = 1 AND m.disqualified = 0
    ORDER BY invites DESC, reached_at ASC, m.user_id ASC;
    """
    async with _connect(db_path) as db:
        async with db.execute(sql) as cur:
            rows = await cur.fetchall()
    return [
        {
            "rank": i,
            "user_id": r[0],
            "username": r[1],
            "invites": int(r[2]),
            "downloads": int(r[4]),
            "pending": int(r[5]),
        }
        for i, r in enumerate(rows, start=1)
    ]


def is_qualified(row: Dict[str, Any], min_invites: int) -> bool:
    return row["invites"] >= min_invites and row["downloads"] >= 1


async def get_winners(db_path: str) -> List[Dict[str, Any]]:
    async with _connect(db_path) as db:
        async with db.execute(
            """
            SELECT w.user_id, w.place, w.kind, w.invites, w.notified, u.username
            FROM contest_winners w LEFT JOIN users u ON u.user_id = w.user_id
            ORDER BY w.place ASC;
            """
        ) as cur:
            rows = await cur.fetchall()
    return [
        {"user_id": r[0], "place": r[1], "kind": r[2], "invites": r[3], "notified": bool(r[4]), "username": r[5]}
        for r in rows
    ]


async def draw_winners(db_path: str, rng: Optional[random.Random] = None) -> List[Dict[str, Any]]:
    """Pick the winners and mark the contest as ended."""
    rng = rng or random.SystemRandom()
    cfg = await get_contest(db_path)
    qualified = [r for r in await get_standings(db_path) if is_qualified(r, cfg["min_invites"])]
    chosen: List[Dict[str, Any]] = []
    if qualified:
        chosen.append({**qualified[0], "place": 1, "kind": "top"})
        rest = qualified[1:]
        for row in rng.sample(rest, min(max(cfg["winners_count"] - 1, 0), len(rest))):
            chosen.append({**row, "place": len(chosen) + 1, "kind": "random"})
        chosen = chosen[: cfg["winners_count"]]
    async with _connect(db_path) as db:
        await db.execute("DELETE FROM contest_winners;")
        for w in chosen:
            await db.execute(
                "INSERT INTO contest_winners (user_id, place, kind, invites) VALUES (?, ?, ?, ?);",
                (w["user_id"], w["place"], w["kind"], w["invites"]),
            )
        await db.execute("UPDATE contest SET status = 'ended' WHERE id = 1;")
        await db.commit()
    return await get_winners(db_path)


async def finish_contest(db_path: str, rng: Optional[random.Random] = None) -> Optional[List[Dict[str, Any]]]:
    """End a running contest now. None when no contest is running."""
    if (await get_contest(db_path))["status"] != "running":
        return None
    return await draw_winners(db_path, rng)


async def disqualify(
    db_path: str, user_id: int, rng: Optional[random.Random] = None
) -> Optional[Dict[str, Any]]:
    """Remove a participant (e.g. fake invites). A removed winner is replaced when someone qualified is left."""
    rng = rng or random.SystemRandom()
    async with _connect(db_path) as db:
        await db.execute("UPDATE contest_members SET disqualified = 1 WHERE user_id = ?;", (user_id,))
        async with db.execute("SELECT place, kind FROM contest_winners WHERE user_id = ?;", (user_id,)) as cur:
            removed = await cur.fetchone()
        await db.execute("DELETE FROM contest_winners WHERE user_id = ?;", (user_id,))
        await db.commit()
    cfg = await get_contest(db_path)
    if not removed or cfg["status"] != "ended":
        return None
    taken = {w["user_id"] for w in await get_winners(db_path)}
    candidates = [
        r for r in await get_standings(db_path) if is_qualified(r, cfg["min_invites"]) and r["user_id"] not in taken
    ]
    if not candidates:
        return None
    pick = candidates[0] if removed[1] == "top" else rng.choice(candidates)
    async with _connect(db_path) as db:
        await db.execute(
            "INSERT INTO contest_winners (user_id, place, kind, invites) VALUES (?, ?, ?, ?);",
            (pick["user_id"], removed[0], removed[1], pick["invites"]),
        )
        await db.commit()
    return pick


async def notify_winners(bot: Bot, db_path: str) -> int:
    """Send the congratulation to every winner not yet told. Returns how many messages went out."""
    sent = 0
    for w in await get_winners(db_path):
        if w["notified"]:
            continue
        try:
            await bot.send_message(w["user_id"], texts.CT_WINNER_MSG.format(prize=texts.CONTEST_PRIZE), parse_mode="HTML")
        except Exception as e:  # noqa: BLE001 - winner may have blocked the bot; admin sees "not notified"
            logger.warning("Could not notify contest winner %s: %s", w["user_id"], e)
            continue
        async with _connect(db_path) as db:
            await db.execute("UPDATE contest_winners SET notified = 1 WHERE user_id = ?;", (w["user_id"],))
            await db.commit()
        sent += 1
    return sent


async def run_contest_once(bot: Bot, db_path: str) -> bool:
    """If the running contest has expired: draw winners and show the result to the admins."""
    cfg = await get_contest(db_path)
    if cfg["status"] != "running" or cfg["seconds_left"] > 0:
        return False
    await finish_contest(db_path)
    # Imported here: the renderer lives with the handlers.
    from app.handlers.contest import render_result

    text, markup = await render_result(db_path)
    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, texts.CT_FINISHED_HEAD + text, reply_markup=markup, parse_mode="HTML")
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not send contest result to admin %s: %s", admin_id, e)
    await finalize_posts(bot, db_path, texts.CT_POST_ENDED)  # slow (paced edits), so after the admins know
    return True


async def run_contest_scheduler(bot: Bot, db_path: str) -> None:
    logger.info("Contest scheduler started.")
    while True:
        try:
            await run_contest_once(bot, db_path)
            await run_post_tick(bot, db_path)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("Contest tick crashed")
        await asyncio.sleep(TICK_SECONDS)


def contest_link(bot_username: str) -> str:
    """Deep link: opens the bot, starts it and shows the contest rules."""
    return f"https://t.me/{bot_username}?start={START_PAYLOAD}"


async def broadcast_announcement(bot: Bot, db_path: str, text: str) -> Dict[str, int]:
    """Send the contest announcement (with a 'join' button) to every known user."""
    me = await bot.me()
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.CT_ANNOUNCE_BTN, url=contest_link(me.username or ""))]]
    )
    sent = blocked = 0
    for uid in await get_all_user_ids(db_path):
        try:
            await bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.04)  # ~25 messages/second to stay under flood limits
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
            try:
                await bot.send_message(uid, text, reply_markup=markup, parse_mode="HTML")
                sent += 1
            except Exception:  # noqa: BLE001
                blocked += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            blocked += 1
            await remove_user(db_path, uid)  # blocked the bot / deleted account
        except Exception as e:  # noqa: BLE001
            logger.debug("Contest announcement to %s failed: %s", uid, e)
            blocked += 1
    return {"sent": sent, "blocked": blocked}


# ---------------------------------------------------------------- calendar (Tashkent time)


def tashkent_today() -> date:
    return datetime.now(TZ).date()


def end_date(cfg: Dict[str, Any]) -> Optional[date]:
    """The date on whose 00:00 (Tashkent) the contest ends, i.e. the day after the last contest day."""
    if not cfg.get("ends_at"):
        return None
    ends = datetime.strptime(cfg["ends_at"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
    return ends.astimezone(TZ).date()


def days_left(cfg: Dict[str, Any], today: Optional[date] = None) -> int:
    end = end_date(cfg)
    if end is None:
        return 0
    return max((end - (today or tashkent_today())).days, 0)


def date_label(d: date) -> str:
    return f"{d.day}-{UZ_MONTHS[d.month - 1]}"


def last_day_label(cfg: Dict[str, Any]) -> str:
    """The last day people can still take part, e.g. '1-dekabr'."""
    end = end_date(cfg)
    return date_label(end - timedelta(days=1)) if end else ""


def left_text(cfg: Dict[str, Any], today: Optional[date] = None) -> str:
    """'15 kun', '1 kun (bugun oxirgi kun!)' ... recalculated from the calendar every time it is shown."""
    n = days_left(cfg, today)
    if n >= 2:
        return f"{n} kun"
    if n == 1:
        return texts.CT_LAST_DAY
    return texts.CT_FEW_HOURS


# ---------------------------------------------------------------- channel / group post


_POST_FIELDS = {
    "enabled", "chat_id", "chat_title", "kind", "body", "file_id",
    "interval_h", "last_sent_ts", "last_edit_date", "last_error",
}


async def get_post(db_path: str) -> Dict[str, Any]:
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest_post (id) VALUES (1);")
        await db.commit()
        async with db.execute(
            "SELECT enabled, chat_id, chat_title, kind, body, file_id, interval_h, last_sent_ts, "
            "last_edit_date, last_error FROM contest_post WHERE id = 1;"
        ) as cur:
            r = await cur.fetchone()
    return {
        "enabled": bool(r[0]), "chat_id": r[1], "chat_title": r[2], "kind": r[3], "body": r[4],
        "file_id": r[5], "interval_h": int(r[6]), "last_sent_ts": int(r[7]),
        "last_edit_date": r[8], "last_error": r[9],
    }


async def update_post(db_path: str, **fields: Any) -> None:
    unknown = set(fields) - _POST_FIELDS
    if unknown:
        raise ValueError(f"Unknown contest_post fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{k} = ?" for k in fields)
    values = [int(v) if isinstance(v, bool) else v for v in fields.values()]
    async with _connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO contest_post (id) VALUES (1);")
        await db.execute(f"UPDATE contest_post SET {assignments} WHERE id = 1;", values)
        await db.commit()


async def _tracked_posts(db_path: str) -> List[Dict[str, Any]]:
    async with _connect(db_path) as db:
        async with db.execute(
            "SELECT chat_id, message_id, kind, body FROM contest_posts ORDER BY rowid DESC LIMIT ?;",
            (MAX_TRACKED_POSTS,),
        ) as cur:
            rows = await cur.fetchall()
    return [{"chat_id": r[0], "message_id": r[1], "kind": r[2], "body": r[3]} for r in rows]


async def _track_post(db_path: str, chat_id: str, message_id: int, kind: str, body: str) -> None:
    async with _connect(db_path) as db:
        await db.execute(
            "INSERT OR REPLACE INTO contest_posts (chat_id, message_id, kind, body) VALUES (?, ?, ?, ?);",
            (chat_id, message_id, kind, body),
        )
        await db.commit()


async def _untrack_post(db_path: str, chat_id: str, message_id: int) -> None:
    async with _connect(db_path) as db:
        await db.execute("DELETE FROM contest_posts WHERE chat_id = ? AND message_id = ?;", (chat_id, message_id))
        await db.commit()


def _chat_arg(chat_id: Any) -> Any:
    try:
        return int(chat_id)
    except (TypeError, ValueError):
        return chat_id


def post_text(body: str, cfg: Dict[str, Any], today: Optional[date] = None) -> str:
    """The admin's text plus the live countdown line (it is refreshed every midnight)."""
    return body + texts.CT_POST_FOOTER.format(left=left_text(cfg, today), last=last_day_label(cfg))


async def _join_markup(bot: Bot) -> InlineKeyboardMarkup:
    me = await bot.me()
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.CT_ANNOUNCE_BTN, url=contest_link(me.username or ""))]]
    )


async def send_post(bot: Bot, db_path: str, post: Dict[str, Any], cfg: Dict[str, Any]) -> int:
    """Publish the saved post in the chosen channel/group and remember it for the daily refresh."""
    text = post_text(post["body"] or "", cfg)
    markup = await _join_markup(bot)
    chat = _chat_arg(post["chat_id"])
    if post["kind"] == "photo":
        msg = await bot.send_photo(chat, post["file_id"], caption=text, reply_markup=markup, parse_mode="HTML")
    elif post["kind"] == "video":
        msg = await bot.send_video(chat, post["file_id"], caption=text, reply_markup=markup, parse_mode="HTML")
    else:
        msg = await bot.send_message(chat, text, reply_markup=markup, parse_mode="HTML")
    await _track_post(db_path, str(post["chat_id"]), msg.message_id, post["kind"] or "text", post["body"] or "")
    return msg.message_id


async def send_post_now(bot: Bot, db_path: str) -> Optional[str]:
    """Send the post right away. Returns an error text, or None on success."""
    cfg = await get_contest(db_path)
    post = await get_post(db_path)
    if not cfg["active"]:
        return texts.CT_ANNOUNCE_NOT_ACTIVE
    if not post["chat_id"] or not post["body"] and not post["file_id"]:
        return texts.CT_POST_NOT_READY
    await update_post(db_path, last_sent_ts=int(time.time()))
    try:
        await send_post(bot, db_path, post, cfg)
    except Exception as e:  # noqa: BLE001 - show any Telegram error to the admin
        logger.warning("Contest post to %s failed: %s", post["chat_id"], e)
        await update_post(db_path, last_error=str(e)[:200])
        return str(e)[:200]
    await update_post(db_path, last_error=None)
    return None


async def _edit_one(bot: Bot, row: Dict[str, Any], text: str, markup: InlineKeyboardMarkup) -> str:
    """Edit one old post. Returns 'ok', 'gone' (message deleted or not editable) or 'error'."""
    chat = _chat_arg(row["chat_id"])
    for attempt in range(2):
        try:
            if row["kind"] in ("photo", "video"):
                await bot.edit_message_caption(
                    chat_id=chat, message_id=row["message_id"], caption=text, reply_markup=markup, parse_mode="HTML"
                )
            else:
                await bot.edit_message_text(
                    text, chat_id=chat, message_id=row["message_id"], reply_markup=markup, parse_mode="HTML"
                )
            return "ok"
        except TelegramRetryAfter as e:
            if attempt == 0:
                await asyncio.sleep(e.retry_after + 1)
                continue
            return "error"
        except TelegramBadRequest as e:
            if "not modified" in str(e).lower():
                return "ok"
            return "gone"
        except Exception as e:  # noqa: BLE001
            logger.warning("Could not refresh contest post %s/%s: %s", row["chat_id"], row["message_id"], e)
            return "error"
    return "error"


async def refresh_posts(
    bot: Bot,
    db_path: str,
    cfg: Dict[str, Any],
    today: Optional[date] = None,
    note: Optional[str] = None,
) -> int:
    """Rewrite every earlier post with today's countdown (or, with `note`, with a closing line and no button)."""
    rows = await _tracked_posts(db_path)
    if not rows:
        return 0
    markup = InlineKeyboardMarkup(inline_keyboard=[]) if note else await _join_markup(bot)
    edited = 0
    for i, row in enumerate(rows):
        text = (
            row["body"] + texts.CT_POST_FOOTER_DONE.format(note=note)
            if note
            else post_text(row["body"], cfg, today)
        )
        result = await _edit_one(bot, row, text, markup)
        if result == "gone":
            await _untrack_post(db_path, row["chat_id"], row["message_id"])
        elif result == "ok":
            edited += 1
        if i < len(rows) - 1:
            await asyncio.sleep(EDIT_PAUSE)
    return edited


async def finalize_posts(bot: Bot, db_path: str, note: str) -> None:
    """Contest over: close every post ("Konkurs yakunlandi!"), drop the button and stop posting."""
    cfg = await get_contest(db_path)
    await refresh_posts(bot, db_path, cfg, note=note)
    async with _connect(db_path) as db:
        await db.execute("DELETE FROM contest_posts;")
        await db.commit()
    await update_post(db_path, enabled=False)


async def run_post_tick(
    bot: Bot, db_path: str, now: Optional[float] = None, today: Optional[date] = None
) -> None:
    """Midnight refresh of old posts, then a new post when the interval has passed."""
    cfg = await get_contest(db_path)
    if not cfg["active"]:
        return
    post = await get_post(db_path)
    today = today or tashkent_today()
    now = time.time() if now is None else now

    if post["last_edit_date"] != today.isoformat():
        await update_post(db_path, last_edit_date=today.isoformat())
        if post["last_edit_date"] is not None:
            await refresh_posts(bot, db_path, cfg, today)

    if (
        post["enabled"]
        and post["chat_id"]
        and (post["body"] or post["file_id"])
        and now - post["last_sent_ts"] >= post["interval_h"] * 3600
    ):
        await send_post_now(bot, db_path)
