"""Contest countdown (Tashkent calendar), the channel/group post and its midnight refresh, and the admin wizard."""

import itertools
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest
from aiogram.exceptions import TelegramBadRequest

from app.config import settings
from app.db import init_db
from app.services import contest as ct


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


@pytest.fixture(autouse=True)
def _no_pause(monkeypatch):
    monkeypatch.setattr(ct, "EDIT_PAUSE", 0)


def _bot():
    ids = itertools.count(100)
    bot = MagicMock()
    bot.me = AsyncMock(return_value=MagicMock(username="my_bot"))

    async def sent(*a, **k):
        return MagicMock(message_id=next(ids))

    bot.send_message = AsyncMock(side_effect=sent)
    bot.send_photo = AsyncMock(side_effect=sent)
    bot.send_video = AsyncMock(side_effect=sent)
    bot.edit_message_text = AsyncMock()
    bot.edit_message_caption = AsyncMock()
    return bot


async def _running_with_post(db_path, kind="text", body="Konkurs! Qatnashing", file_id=None, interval_h=6):
    await init_db(db_path)
    await ct.start_contest(db_path)
    await ct.update_post(
        db_path, enabled=True, chat_id="-1001", chat_title="Kanal", kind=kind, body=body,
        file_id=file_id, interval_h=interval_h,
    )


def _today():
    return ct.tashkent_today()


# ---------------------------------------------------------------- countdown


async def test_days_left_drops_by_one_each_tashkent_day(db_path):
    await init_db(db_path)
    async with aiosqlite.connect(db_path) as db:   # ends at 00:00 on 2-dekabr, Tashkent (= 19:00 UTC on 1 Dec)
        await db.execute("INSERT OR IGNORE INTO contest (id) VALUES (1);")
        await db.execute("UPDATE contest SET ends_at = '2026-12-01 19:00:00.000' WHERE id = 1;")
        await db.commit()
    cfg = await ct.get_contest(db_path)
    from datetime import date

    assert ct.days_left(cfg, date(2026, 11, 17)) == 15
    assert ct.days_left(cfg, date(2026, 11, 18)) == 14
    assert ct.left_text(cfg, date(2026, 11, 18)) == "14 kun"
    assert "oxirgi kun" in ct.left_text(cfg, date(2026, 12, 1))
    assert ct.days_left(cfg, date(2026, 12, 2)) == 0
    assert ct.last_day_label(cfg) == "1-dekabr"


async def test_contest_ends_at_tashkent_midnight_after_the_chosen_days(db_path):
    await init_db(db_path)
    await ct.update_settings(db_path, days=15)
    await ct.start_contest(db_path)
    cfg = await ct.get_contest(db_path)
    ends = datetime.strptime(cfg["ends_at"], "%Y-%m-%d %H:%M:%S.%f").replace(tzinfo=timezone.utc).astimezone(ct.TZ)
    assert (ends.hour, ends.minute, ends.second) == (0, 0, 0)
    assert ends.date() == _today() + timedelta(days=15)
    assert ct.days_left(cfg) == 15            # right after the start: the full 15 days


# ---------------------------------------------------------------- posting


async def test_post_goes_out_at_the_chosen_interval(db_path):
    await _running_with_post(db_path, interval_h=6)
    bot = _bot()
    now = time.time()
    await ct.run_post_tick(bot, db_path, now=now)
    assert bot.send_message.await_count == 1
    sent_text = bot.send_message.await_args.args[1]
    assert "Konkurs! Qatnashing" in sent_text and "15 kun qoldi" in sent_text
    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://t.me/my_bot?start=konkurs"

    await ct.run_post_tick(bot, db_path, now=now + 60)                 # too early
    assert bot.send_message.await_count == 1
    await ct.run_post_tick(bot, db_path, now=time.time() + 6 * 3600 + 5)
    assert bot.send_message.await_count == 2


async def test_photo_post_uses_caption(db_path):
    await _running_with_post(db_path, kind="photo", body="Rasm izohi", file_id="FILE1")
    bot = _bot()
    await ct.run_post_tick(bot, db_path)
    assert bot.send_photo.await_count == 1
    assert bot.send_photo.await_args.args[:2] == (-1001, "FILE1")
    assert "Rasm izohi" in bot.send_photo.await_args.kwargs["caption"]


async def test_old_posts_get_one_day_less_at_midnight_only_once(db_path):
    await _running_with_post(db_path, interval_h=1)
    bot = _bot()
    await ct.run_post_tick(bot, db_path, now=time.time())
    await ct.run_post_tick(bot, db_path, now=time.time() + 3601)       # second post, same day
    assert bot.send_message.await_count == 2
    assert bot.edit_message_text.await_count == 0                      # nothing stale yet

    tomorrow = _today() + timedelta(days=1)
    await ct.run_post_tick(bot, db_path, now=time.time(), today=tomorrow)
    assert bot.edit_message_text.await_count == 2                      # both old posts refreshed
    for call in bot.edit_message_text.await_args_list:
        assert "14 kun qoldi" in call.args[0]

    await ct.run_post_tick(bot, db_path, now=time.time(), today=tomorrow)
    assert bot.edit_message_text.await_count == 2                      # same day: no repeat


async def test_media_posts_are_refreshed_through_the_caption(db_path):
    await _running_with_post(db_path, kind="video", body="Video", file_id="V1")
    bot = _bot()
    await ct.run_post_tick(bot, db_path)
    await ct.run_post_tick(bot, db_path, today=_today() + timedelta(days=1))
    assert bot.edit_message_caption.await_count == 1
    assert "14 kun qoldi" in bot.edit_message_caption.await_args.kwargs["caption"]
    assert bot.edit_message_text.await_count == 0


async def test_deleted_post_is_forgotten_instead_of_retried(db_path):
    await _running_with_post(db_path)
    bot = _bot()
    await ct.run_post_tick(bot, db_path)
    bot.edit_message_text.side_effect = TelegramBadRequest(
        method=MagicMock(), message="Bad Request: message to edit not found"
    )
    await ct.run_post_tick(bot, db_path, today=_today() + timedelta(days=1))
    bot.edit_message_text.reset_mock()
    await ct.run_post_tick(bot, db_path, today=_today() + timedelta(days=2))
    assert bot.edit_message_text.await_count == 0


async def test_failed_send_is_reported_not_raised(db_path):
    await _running_with_post(db_path)
    bot = _bot()
    bot.send_message.side_effect = RuntimeError("bot is not a member of the channel chat")
    error = await ct.send_post_now(bot, db_path)
    assert "not a member" in error
    assert "not a member" in (await ct.get_post(db_path))["last_error"]
    bot.send_message.side_effect = None
    bot.send_message.return_value = MagicMock(message_id=555)
    assert await ct.send_post_now(bot, db_path) is None
    assert (await ct.get_post(db_path))["last_error"] is None


async def test_nothing_is_posted_or_edited_when_contest_is_not_active(db_path):
    await _running_with_post(db_path)
    await ct.cancel_contest(db_path)
    bot = _bot()
    await ct.run_post_tick(bot, db_path, today=_today() + timedelta(days=1))
    assert bot.send_message.await_count == 0 and bot.edit_message_text.await_count == 0
    assert await ct.send_post_now(bot, db_path)                        # returns the "not active" error text


async def test_finalize_closes_posts_removes_button_and_stops_posting(db_path):
    await _running_with_post(db_path)
    bot = _bot()
    await ct.run_post_tick(bot, db_path)
    await ct.finalize_posts(bot, db_path, "Konkurs yakunlandi!")
    call = bot.edit_message_text.await_args
    assert "Konkurs yakunlandi!" in call.args[0] and "qoldi" not in call.args[0]
    assert call.kwargs["reply_markup"].inline_keyboard == []
    assert (await ct.get_post(db_path))["enabled"] is False
    bot.edit_message_text.reset_mock()
    await ct.finalize_posts(bot, db_path, "x")                         # nothing tracked any more
    assert bot.edit_message_text.await_count == 0


async def test_post_texts_never_hardcode_the_day_count():
    from app import texts

    assert "15" not in texts.CT_RULES and "15" not in texts.CT_ANNOUNCE
    assert "{left}" in texts.CT_RULES and "{left}" in texts.CT_POST_FOOTER


# ---------------------------------------------------------------- admin wizard


def _admin_cb(data, bot=None):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 777
    cb.bot = bot or _bot()
    cb.message.edit_text = AsyncMock()
    cb.answer = AsyncMock()
    return cb


def _state():
    st = MagicMock()
    st.set_state = AsyncMock()
    st.clear = AsyncMock()
    return st


async def test_wizard_end_to_end(db_path, monkeypatch):
    from app.db import add_channel
    from app.handlers import contest as h

    await init_db(db_path)
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "777")
    await add_channel(db_path, "-1001234", "Kanalim", "https://t.me/x")
    bot = _bot()
    state = _state()

    # step 1: days
    await h.callback_contest_start_days(_admin_cb("contest:sd:7", bot))
    assert (await ct.get_contest(db_path))["days"] == 7
    assert (await ct.get_contest(db_path))["status"] != "running"      # nothing started yet

    # step 2: channel
    channels = [c for c in await __import__("app.db", fromlist=["get_channels"]).get_channels(db_path)]
    await h.callback_contest_post_chat(_admin_cb(f"contest:pc:{channels[0]['id']}", bot), state)
    state.set_state.assert_awaited_once_with(h.ContestStates.waiting_post)
    assert (await ct.get_post(db_path))["chat_id"] == "-1001234"

    # step 3: the admin's text (formatting kept as HTML)
    msg = MagicMock()
    msg.from_user.id = 777
    msg.photo = None
    msg.video = None
    msg.text = "Konkurs bor"
    msg.html_text = "<b>Konkurs</b> bor"
    msg.reply = AsyncMock()
    await h.process_post_content(msg, state)
    post = await ct.get_post(db_path)
    assert post["kind"] == "text" and post["body"] == "<b>Konkurs</b> bor"

    # step 4: interval -> contest starts and the first post goes out immediately
    cb = _admin_cb("contest:pi:3", bot)
    await h.callback_contest_post_interval(cb)
    cfg = await ct.get_contest(db_path)
    assert cfg["status"] == "running" and cfg["days"] == 7
    assert ct.days_left(cfg) == 7
    assert (await ct.get_post(db_path))["interval_h"] == 3
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.args[0] == -1001234


async def test_wizard_can_start_without_a_channel_post(db_path, monkeypatch):
    from app.handlers import contest as h

    await init_db(db_path)
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "777")
    bot = _bot()
    await h.callback_contest_post_chat(_admin_cb("contest:pc:0", bot), _state())
    assert (await ct.get_contest(db_path))["status"] == "running"
    assert (await ct.get_post(db_path))["enabled"] is False
    await ct.run_post_tick(bot, db_path)
    assert bot.send_message.await_count == 0


async def test_post_content_validation(db_path, monkeypatch):
    from app.handlers import contest as h

    await init_db(db_path)
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "777")

    def message(**kw):
        m = MagicMock()
        m.from_user.id = 777
        m.photo = kw.get("photo")
        m.video = kw.get("video")
        m.text = kw.get("text")
        m.html_text = kw.get("html", "")
        m.reply = AsyncMock()
        return m

    long_caption = message(photo=[MagicMock(file_id="P")], html="x" * 1000)   # caption limit
    await h.process_post_content(long_caption, _state())
    assert "juda uzun" in long_caption.reply.await_args.args[0]
    assert (await ct.get_post(db_path))["file_id"] is None

    sticker = message()                                                       # neither text, photo nor video
    await h.process_post_content(sticker, _state())
    assert "Faqat matn" in sticker.reply.await_args.args[0]

    photo = message(photo=[MagicMock(file_id="small"), MagicMock(file_id="BIG")], html="Izoh")
    await h.process_post_content(photo, _state())
    post = await ct.get_post(db_path)
    assert (post["kind"], post["file_id"], post["body"]) == ("photo", "BIG", "Izoh")


async def test_only_admins_can_use_the_wizard(db_path, monkeypatch):
    from app.handlers import contest as h

    await init_db(db_path)
    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "777")
    cb = _admin_cb("contest:pi:3")
    cb.from_user.id = 5
    await h.callback_contest_post_interval(cb)
    assert (await ct.get_contest(db_path))["status"] != "running"
