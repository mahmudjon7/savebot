"""Referral contest: user screens (/konkurs, join, rating) and the admin panel."""

import asyncio
import html
import logging
from typing import Any, List, Set, Tuple

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from app import texts
from app.config import settings
from app.db import get_all_user_ids, get_channels, upsert_user
from app.handlers.admin import is_admin
from app.services import contest as ct
from app.services.referral import display_name, make_ref_link, share_url

logger = logging.getLogger(__name__)
router = Router(name="contest")

_MEDALS = ["🥇", "🥈", "🥉"]


class ContestStates(StatesGroup):
    waiting_post = State()


_background: Set[asyncio.Task] = set()


def _run_in_background(coro: Any) -> None:
    """Fire-and-forget (slow Telegram edits must not keep the admin waiting); keep a reference so it isn't GC'd."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


# ---------------------------------------------------------------- users


async def render_user_contest(bot, db_path: str, user_id: int) -> Tuple[str, InlineKeyboardMarkup]:
    cfg = await ct.get_contest(db_path)
    if not cfg["active"]:
        return texts.CT_NONE, InlineKeyboardMarkup(inline_keyboard=[])
    text = texts.CT_RULES.format(
        prize=texts.CONTEST_PRIZE,
        min=cfg["min_invites"],
        winners=cfg["winners_count"],
        left=ct.left_text(cfg),
        last=ct.last_day_label(cfg),
    )
    member = await ct.get_member(db_path, user_id)
    rows: List[List[InlineKeyboardButton]] = []
    if member is None:
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_JOIN, callback_data="ct:join")])
    elif member["disqualified"]:
        text += texts.CT_DISQUALIFIED
    else:
        standings = await ct.get_standings(db_path)
        mine = next((r for r in standings if r["user_id"] == user_id), None)
        me = await bot.me()
        link = make_ref_link(me.username or "", user_id)
        text += texts.CT_MEMBER_INFO.format(
            count=mine["invites"] if mine else 0,
            min=cfg["min_invites"],
            rank=mine["rank"] if mine else "-",
            pending_line=(
                texts.CT_PENDING_LINE.format(count=mine["pending"]) if mine and mine["pending"] else ""
            ),
            dl_line=texts.CT_NEED_DOWNLOAD if mine and mine["downloads"] < 1 else "",
            link=link,
        )
        rows.append([InlineKeyboardButton(text=texts.REF_BTN_SHARE, url=share_url(link))])
    rows.append([InlineKeyboardButton(text=texts.CT_BTN_TOP, callback_data="ct:top")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def render_user_top(db_path: str, user_id: int) -> str:
    standings = [r for r in await ct.get_standings(db_path) if r["invites"] > 0]
    if not standings:
        return texts.CT_TOP_TITLE.format(rows=texts.CT_TOP_EMPTY)
    rows = []
    for r in standings[:10]:
        medal = _MEDALS[r["rank"] - 1] if r["rank"] <= len(_MEDALS) else f"{r['rank']}."
        rows.append(
            texts.CT_TOP_ROW.format(
                medal=medal, name=display_name(r["username"], r["user_id"]), count=r["invites"]
            )
        )
    return texts.CT_TOP_TITLE.format(rows="\n".join(rows))


@router.message(Command("konkurs"))
async def handle_contest_command(message: Message) -> None:
    if not message.from_user:
        return
    if message.chat.type == "private":
        await upsert_user(settings.db_path, message.from_user.id, message.from_user.username)
    text, markup = await render_user_contest(message.bot, settings.db_path, message.from_user.id)
    await message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "ct:me")
async def callback_contest_open(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    if callback.message.chat.type == "private":
        await upsert_user(settings.db_path, callback.from_user.id, callback.from_user.username)
    text, markup = await render_user_contest(callback.bot, settings.db_path, callback.from_user.id)
    await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "ct:join")
async def callback_contest_join(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    if callback.message.chat.type != "private":
        await callback.answer(texts.CT_PRIVATE_ONLY_TOAST, show_alert=True)
        return
    await upsert_user(settings.db_path, callback.from_user.id, callback.from_user.username)
    if not await ct.is_contest_active(settings.db_path):
        await callback.answer(texts.CT_NOT_ACTIVE_TOAST, show_alert=True)
        return
    joined = await ct.join_contest(settings.db_path, callback.from_user.id)
    await callback.answer(texts.CT_JOINED_TOAST if joined else texts.CT_ALREADY_TOAST)
    text, markup = await render_user_contest(callback.bot, settings.db_path, callback.from_user.id)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:  # noqa: BLE001 - e.g. "message is not modified"
        await callback.message.answer(text, reply_markup=markup, parse_mode="HTML")


@router.callback_query(F.data == "ct:top")
async def callback_contest_top(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    await callback.message.answer(await render_user_top(settings.db_path, callback.from_user.id), parse_mode="HTML")
    await callback.answer()


# ---------------------------------------------------------------- admin


def _admin_name(username, user_id: int) -> str:
    label = ("@" + html.escape(username)) if username else str(user_id)
    return f'<a href="tg://user?id={user_id}">{label}</a>'


async def render_contest_menu(db_path: str, bot=None) -> Tuple[str, InlineKeyboardMarkup]:
    cfg = await ct.get_contest(db_path)
    status = {
        "running": texts.CT_STATUS_RUNNING,
        "ended": texts.CT_STATUS_ENDED,
    }.get(cfg["status"], texts.CT_STATUS_OFF)
    extra = ""
    if cfg["status"] == "running":
        extra += texts.CT_EXTRA_LEFT.format(left=ct.left_text(cfg), last=ct.last_day_label(cfg))
        post = await ct.get_post(db_path)
        if post["enabled"] and post["chat_id"]:
            extra += texts.CT_EXTRA_POST.format(
                chat=html.escape(post["chat_title"] or str(post["chat_id"])), h=post["interval_h"]
            )
        else:
            extra += texts.CT_EXTRA_POST_OFF
        if post["last_error"]:
            extra += texts.CT_EXTRA_POST_ERROR.format(error=html.escape(post["last_error"]))
        if bot is not None:
            extra += texts.CT_EXTRA_LINK.format(link=ct.contest_link((await bot.me()).username or ""))
    if cfg["status"] in ("running", "ended"):
        standings = await ct.get_standings(db_path)
        extra += texts.CT_EXTRA_QUALIFIED.format(
            count=sum(1 for r in standings if ct.is_qualified(r, cfg["min_invites"]))
        )
    text = texts.CT_ADMIN_MENU.format(
        status=status,
        prize=texts.CONTEST_PRIZE,
        min=cfg["min_invites"],
        winners=cfg["winners_count"],
        days=cfg["days"],
        members=cfg["members"],
        extra=extra,
    )
    rows: List[List[InlineKeyboardButton]] = []
    if cfg["status"] == "running":
        rows.append(
            [
                InlineKeyboardButton(text=texts.CT_BTN_FINISH, callback_data="contest:finish"),
                InlineKeyboardButton(text=texts.CT_BTN_CANCEL, callback_data="contest:cancel"),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(text=texts.CT_BTN_POST, callback_data="contest:post"),
                InlineKeyboardButton(text=texts.CT_BTN_POST_NOW, callback_data="contest:postnow"),
            ]
        )
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_ANNOUNCE, callback_data="contest:announce")])
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_ADMIN_TOP, callback_data="contest:top")])
    else:
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_START, callback_data="contest:start")])
        if cfg["status"] == "ended":
            rows.append([InlineKeyboardButton(text=texts.CT_BTN_RESULT, callback_data="contest:result")])
    rows.append(
        [
            InlineKeyboardButton(text=texts.CT_BTN_SET_MIN.format(n=cfg["min_invites"]), callback_data="contest:pick:min"),
            InlineKeyboardButton(text=texts.CT_BTN_SET_DAYS.format(n=cfg["days"]), callback_data="contest:pick:days"),
        ]
    )
    rows.append(
        [InlineKeyboardButton(text=texts.CT_BTN_SET_WIN.format(n=cfg["winners_count"]), callback_data="contest:pick:win")]
    )
    rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="admin:menu")])
    return text, InlineKeyboardMarkup(inline_keyboard=rows)


async def render_result(db_path: str) -> Tuple[str, InlineKeyboardMarkup]:
    winners = await ct.get_winners(db_path)
    rows_text = []
    buttons: List[List[InlineKeyboardButton]] = []
    for w in winners:
        rows_text.append(
            texts.CT_RESULT_ROW.format(
                place=w["place"],
                name=_admin_name(w["username"], w["user_id"]),
                count=w["invites"],
                kind=texts.CT_KIND_TOP if w["kind"] == "top" else texts.CT_KIND_RANDOM,
                notified=texts.CT_NOTIFIED_MARK if w["notified"] else "",
            )
        )
        label = ("@" + w["username"]) if w["username"] else str(w["user_id"])
        buttons.append(
            [InlineKeyboardButton(text=texts.CT_BTN_DQ.format(name=label), callback_data=f"contest:dq:{w['user_id']}")]
        )
    body = "\n".join(rows_text) if rows_text else texts.CT_RESULT_EMPTY
    if winners:
        buttons.append([InlineKeyboardButton(text=texts.CT_BTN_NOTIFY, callback_data="contest:notify")])
    buttons.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")])
    return texts.CT_RESULT_TITLE.format(rows=body), InlineKeyboardMarkup(inline_keyboard=buttons)


async def _guard(callback: CallbackQuery) -> bool:
    if not callback.from_user or not is_admin(callback.from_user.id) or not callback.message:
        await callback.answer(texts.ADMIN_ONLY, show_alert=True)
        return False
    return True


async def _show_menu(callback: CallbackQuery) -> None:
    text, markup = await render_contest_menu(settings.db_path, callback.bot)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:  # noqa: BLE001 - "message is not modified"
        pass


@router.callback_query(F.data == "contest:menu")
async def callback_contest_menu(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback):
        return
    await state.clear()
    await _show_menu(callback)
    await callback.answer()


def _picker_rows(buttons: List[InlineKeyboardButton], per_row: int = 3) -> List[List[InlineKeyboardButton]]:
    return [buttons[i : i + per_row] for i in range(0, len(buttons), per_row)]


def _back_row() -> List[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")]


@router.callback_query(F.data == "contest:start")
async def callback_contest_start(callback: CallbackQuery) -> None:
    """Step 1/3 of the start wizard: how many days the contest lasts."""
    if not await _guard(callback):
        return
    buttons = [
        InlineKeyboardButton(text=f"{n} kun", callback_data=f"contest:sd:{n}") for n in ct.DAYS_CHOICES
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=_picker_rows(buttons) + [_back_row()])
    await callback.message.edit_text(texts.CT_PICK_START_DAYS, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


async def _show_post_chat_picker(message: Message, allow_skip: bool) -> None:
    """Step 2/3: which channel or group the announcement goes to (the ones the bot administers)."""
    channels = await get_channels(settings.db_path)
    rows: List[List[InlineKeyboardButton]] = [
        [InlineKeyboardButton(text=f"📢 {ch['title'] or ch['channel_id']}", callback_data=f"contest:pc:{ch['id']}")]
        for ch in channels
    ]
    if allow_skip:
        rows.append([InlineKeyboardButton(text=texts.CT_BTN_NO_POST, callback_data="contest:pc:0")])
    rows.append(_back_row())
    await message.edit_text(
        texts.CT_PICK_POST_CHAT if channels else texts.CT_NO_POST_CHANNELS,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=rows),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("contest:sd:"))
async def callback_contest_start_days(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    raw = callback.data.rsplit(":", 1)[-1]
    if not raw.isdigit() or int(raw) not in ct.DAYS_CHOICES:
        await callback.answer()
        return
    await ct.update_settings(settings.db_path, days=int(raw))
    await _show_post_chat_picker(callback.message, allow_skip=True)
    await callback.answer()


@router.callback_query(F.data == "contest:post")
async def callback_contest_post_setup(callback: CallbackQuery) -> None:
    """Change the channel/group post while the contest is running."""
    if not await _guard(callback):
        return
    await _show_post_chat_picker(callback.message, allow_skip=False)
    await callback.answer()


@router.callback_query(F.data.startswith("contest:pc:"))
async def callback_contest_post_chat(callback: CallbackQuery, state: FSMContext) -> None:
    if not await _guard(callback):
        return
    raw = callback.data.rsplit(":", 1)[-1]
    if not raw.isdigit():
        await callback.answer()
        return
    if raw == "0":  # start without a channel post
        await ct.update_post(settings.db_path, enabled=False)
        if (await ct.get_contest(settings.db_path))["status"] != "running":
            await ct.start_contest(settings.db_path)
        await _show_menu(callback)
        await callback.answer(texts.CT_STARTED_TOAST)
        return
    chosen = next((ch for ch in await get_channels(settings.db_path) if str(ch["id"]) == raw), None)
    if not chosen:
        await callback.answer(texts.CHANNEL_ADD_FAILED.split("\n")[0], show_alert=True)
        return
    await ct.update_post(
        settings.db_path,
        chat_id=str(chosen["channel_id"]),
        chat_title=chosen["title"] or str(chosen["channel_id"]),
        last_error=None,
    )
    await state.set_state(ContestStates.waiting_post)
    await callback.message.edit_text(texts.CT_ASK_POST_CONTENT, parse_mode="HTML")
    await callback.answer()


@router.message(ContestStates.waiting_post)
async def process_post_content(message: Message, state: FSMContext) -> None:
    """Step 3/3: the admin sends the text, photo or video that will be posted."""
    if not message.from_user or not is_admin(message.from_user.id):
        return
    if message.photo:
        kind, file_id, limit = "photo", message.photo[-1].file_id, ct.CAPTION_LIMIT
    elif message.video:
        kind, file_id, limit = "video", message.video.file_id, ct.CAPTION_LIMIT
    elif message.text:
        kind, file_id, limit = "text", None, ct.TEXT_LIMIT
    else:
        await message.reply(texts.CT_POST_BAD_TYPE)
        return
    body = message.html_text or ""
    if len(body) > limit:
        await message.reply(texts.CT_POST_TOO_LONG.format(n=len(body), limit=limit))
        return
    await ct.update_post(settings.db_path, kind=kind, body=body, file_id=file_id, last_error=None)
    await state.clear()
    buttons = [
        InlineKeyboardButton(text=texts.CT_POST_INTERVAL_LABEL.format(h=h), callback_data=f"contest:pi:{h}")
        for h in ct.POST_INTERVAL_CHOICES
    ]
    await message.reply(
        texts.CT_PICK_POST_INTERVAL,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=_picker_rows(buttons, 2) + [_back_row()]),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("contest:pi:"))
async def callback_contest_post_interval(callback: CallbackQuery) -> None:
    """Last step: save the interval, start the contest if it is not running yet and post right away."""
    if not await _guard(callback):
        return
    raw = callback.data.rsplit(":", 1)[-1]
    if not raw.isdigit() or int(raw) not in ct.POST_INTERVAL_CHOICES:
        await callback.answer()
        return
    await ct.update_post(
        settings.db_path, interval_h=int(raw), enabled=True, last_sent_ts=0, last_error=None
    )
    if (await ct.get_contest(settings.db_path))["status"] != "running":
        await ct.start_contest(settings.db_path)
    error = await ct.send_post_now(callback.bot, settings.db_path)
    await _show_menu(callback)
    if error:
        await callback.answer(texts.CT_POST_FAIL.format(error=error), show_alert=True)
    else:
        await callback.answer(texts.CT_STARTED_TOAST)


@router.callback_query(F.data == "contest:postnow")
async def callback_contest_post_now(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    error = await ct.send_post_now(callback.bot, settings.db_path)
    await _show_menu(callback)
    if error:
        await callback.answer(texts.CT_POST_FAIL.format(error=error), show_alert=True)
    else:
        await callback.answer(texts.CT_POST_SENT_OK)


@router.callback_query(F.data == "contest:cancel")
async def callback_contest_cancel(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    await ct.cancel_contest(settings.db_path)
    _run_in_background(ct.finalize_posts(callback.bot, settings.db_path, texts.CT_POST_CANCELLED))
    await _show_menu(callback)
    await callback.answer(texts.CT_CANCELLED_TOAST)


@router.callback_query(F.data == "contest:finish")
async def callback_contest_finish(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    if await ct.finish_contest(settings.db_path) is None:
        await callback.answer(texts.CT_NOT_RUNNING_TOAST, show_alert=True)
        return
    _run_in_background(ct.finalize_posts(callback.bot, settings.db_path, texts.CT_POST_ENDED))
    text, markup = await render_result(settings.db_path)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "contest:announce")
async def callback_contest_announce(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    if not await ct.is_contest_active(settings.db_path):
        await callback.answer(texts.CT_ANNOUNCE_NOT_ACTIVE, show_alert=True)
        return
    count = len(await get_all_user_ids(settings.db_path))
    markup = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=texts.CT_BTN_ANNOUNCE_YES, callback_data="contest:announce:yes")],
            [InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")],
        ]
    )
    await callback.message.edit_text(
        texts.CT_ANNOUNCE_CONFIRM.format(count=count), reply_markup=markup, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "contest:announce:yes")
async def callback_contest_announce_yes(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    cfg = await ct.get_contest(settings.db_path)
    if not cfg["active"]:
        await callback.answer(texts.CT_ANNOUNCE_NOT_ACTIVE, show_alert=True)
        return
    await callback.answer()
    await callback.message.edit_text(texts.BROADCAST_PROGRESS)
    announcement = texts.CT_ANNOUNCE.format(
        prize=texts.CONTEST_PRIZE, winners=cfg["winners_count"], last=ct.last_day_label(cfg)
    )
    result = await ct.broadcast_announcement(callback.bot, settings.db_path, announcement)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")]]
    )
    await callback.message.edit_text(
        texts.CT_ANNOUNCE_DONE.format(sent=result["sent"], blocked=result["blocked"]), reply_markup=markup
    )


@router.callback_query(F.data == "contest:result")
async def callback_contest_result(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    text, markup = await render_result(settings.db_path)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "contest:top")
async def callback_contest_admin_top(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    cfg = await ct.get_contest(settings.db_path)
    rows = [
        texts.CT_ADMIN_TOP_ROW.format(
            mark="✅" if ct.is_qualified(r, cfg["min_invites"]) else "▫️",
            rank=r["rank"],
            name=_admin_name(r["username"], r["user_id"]),
            count=r["invites"],
            dl=r["downloads"],
        )
        for r in (await ct.get_standings(settings.db_path))[:30]
    ]
    text = texts.CT_ADMIN_TOP_TITLE.format(rows="\n".join(rows) if rows else texts.CT_TOP_EMPTY)
    markup = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")]]
    )
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("contest:dq:"))
async def callback_contest_disqualify(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    raw = callback.data.rsplit(":", 1)[-1]
    if not raw.isdigit():
        await callback.answer()
        return
    await ct.disqualify(settings.db_path, int(raw))
    text, markup = await render_result(settings.db_path)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "contest:notify")
async def callback_contest_notify(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    sent = await ct.notify_winners(callback.bot, settings.db_path)
    await callback.answer(texts.CT_NOTIFY_DONE.format(count=sent) if sent else texts.CT_NOTIFY_NONE, show_alert=True)
    text, markup = await render_result(settings.db_path)
    try:
        await callback.message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    except Exception:  # noqa: BLE001
        pass


_PICKERS = {
    "min": (ct.MIN_INVITES_CHOICES, texts.CT_PICK_MIN, "ta"),
    "days": (ct.DAYS_CHOICES, texts.CT_PICK_DAYS, "kun"),
    "win": (ct.WINNERS_CHOICES, texts.CT_PICK_WIN, "ta"),
}


@router.callback_query(F.data.startswith("contest:pick:"))
async def callback_contest_pick(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    what = callback.data.rsplit(":", 1)[-1]
    if what not in _PICKERS:
        await callback.answer()
        return
    choices, title, unit = _PICKERS[what]
    buttons = [
        InlineKeyboardButton(text=f"{n} {unit}", callback_data=f"contest:set:{what}:{n}") for n in choices
    ]
    rows = [buttons[i : i + 3] for i in range(0, len(buttons), 3)]
    rows.append([InlineKeyboardButton(text=texts.ADMIN_BTN_BACK, callback_data="contest:menu")])
    await callback.message.edit_text(title, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("contest:set:"))
async def callback_contest_set(callback: CallbackQuery) -> None:
    if not await _guard(callback):
        return
    parts = callback.data.split(":")
    if len(parts) != 4 or parts[2] not in _PICKERS or not parts[3].isdigit():
        await callback.answer()
        return
    what, value = parts[2], int(parts[3])
    if value not in _PICKERS[what][0]:
        await callback.answer()
        return
    field = {"min": "min_invites", "days": "days", "win": "winners_count"}[what]
    await ct.update_settings(settings.db_path, **{field: value})
    await _show_menu(callback)
    await callback.answer()
