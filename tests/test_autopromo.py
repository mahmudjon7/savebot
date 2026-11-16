"""Tests for the single-chat auto-promo feature (re-posts the admin's last broadcast ad)."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import get_autopromo, init_db, update_autopromo
from app.services.autopromo import (
    ALLOWED_INTERVALS,
    describe_message,
    is_due,
    run_promo_once,
    start_promo,
)


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


def test_is_due_logic():
    base = {
        "enabled": True,
        "chat_id": "-100",
        "src_message_id": 7,
        "interval_min": 5,
        "last_sent_ts": 1000,
    }
    assert not is_due({**base, "enabled": False}, now=999999)
    assert not is_due({**base, "chat_id": None}, now=999999)
    assert not is_due({**base, "src_message_id": None}, now=999999)
    assert not is_due(base, now=1000 + 299)
    assert is_due(base, now=1000 + 300)
    assert {5, 60, 1440} <= ALLOWED_INTERVALS


def test_describe_message_kinds():
    assert describe_message(MagicMock(video=object(), video_note=None)) == "video"
    assert describe_message(MagicMock(video=None, video_note=None, animation=object())) == "GIF"
    assert describe_message(MagicMock(video=None, video_note=None, animation=None, photo=[1])) == "rasm"
    assert describe_message(MagicMock(video=None, video_note=None, animation=None, photo=None, text="x")) == "matn"


async def test_settings_roundtrip(temp_db_path):
    await init_db(temp_db_path)
    cfg = await get_autopromo(temp_db_path)
    assert cfg["enabled"] is False and cfg["chat_id"] is None and cfg["src_message_id"] is None
    assert cfg["interval_min"] == 60
    await update_autopromo(
        temp_db_path, enabled=True, chat_id="-1001", chat_title="Kanal", interval_min=15,
        src_chat_id=42, src_message_id=99, src_kind="video",
    )
    cfg = await get_autopromo(temp_db_path)
    assert cfg["enabled"] is True and cfg["chat_id"] == "-1001" and cfg["interval_min"] == 15
    assert (cfg["src_chat_id"], cfg["src_message_id"], cfg["src_kind"]) == (42, 99, "video")
    with pytest.raises(ValueError):
        await update_autopromo(temp_db_path, bogus=1)


def _fake_bot(exc=None):
    bot = MagicMock()
    bot.copy_message = AsyncMock(side_effect=exc)
    return bot


async def _ready_db(path, **extra):
    await init_db(path)
    await update_autopromo(
        path, enabled=True, chat_id="-1001", interval_min=5, last_sent_ts=0,
        src_chat_id=42, src_message_id=99, src_kind="video", **extra,
    )


async def test_copies_admin_ad_to_selected_chat_when_due(temp_db_path):
    await _ready_db(temp_db_path)
    bot = _fake_bot()
    assert await run_promo_once(bot, temp_db_path) is None
    bot.copy_message.assert_awaited_once_with(chat_id=-1001, from_chat_id=42, message_id=99)
    # Not due again right away.
    assert await run_promo_once(bot, temp_db_path) is None
    assert bot.copy_message.await_count == 1


async def test_nothing_sent_without_ad_or_when_disabled(temp_db_path):
    await init_db(temp_db_path)
    await update_autopromo(temp_db_path, enabled=True, chat_id="-1001", last_sent_ts=0)
    bot = _fake_bot()
    await run_promo_once(bot, temp_db_path)  # no ad saved yet
    assert bot.copy_message.await_count == 0
    await update_autopromo(temp_db_path, enabled=False, src_chat_id=42, src_message_id=99)
    await run_promo_once(bot, temp_db_path)
    assert bot.copy_message.await_count == 0


async def test_error_is_recorded_and_not_spammed(temp_db_path):
    await _ready_db(temp_db_path)
    bot = _fake_bot(exc=RuntimeError("Forbidden: bot is not an admin"))
    err = await run_promo_once(bot, temp_db_path)
    assert "not an admin" in err
    assert (await get_autopromo(temp_db_path))["last_error"]
    await run_promo_once(bot, temp_db_path)
    assert bot.copy_message.await_count == 1  # waits for the next interval


async def test_force_requires_chat_and_ad(temp_db_path):
    await init_db(temp_db_path)
    bot = _fake_bot()
    assert await run_promo_once(bot, temp_db_path, force=True) == "Chat tanlanmagan"
    await update_autopromo(temp_db_path, chat_id="-1001")
    assert "yuborilmagan" in await run_promo_once(bot, temp_db_path, force=True)
    await update_autopromo(temp_db_path, src_chat_id=42, src_message_id=99)
    assert await run_promo_once(bot, temp_db_path, force=True) is None  # works even if disabled
    assert bot.copy_message.await_count == 1


async def test_start_promo_sets_end_time_and_posts_immediately(temp_db_path):
    import time

    await _ready_db(temp_db_path)
    await update_autopromo(temp_db_path, enabled=False, last_sent_ts=int(time.time()), duration_h=5)
    await start_promo(temp_db_path)
    cfg = await get_autopromo(temp_db_path)
    assert cfg["enabled"] and cfg["last_sent_ts"] == 0
    assert abs(cfg["end_ts"] - (time.time() + 5 * 3600)) < 5
    bot = _fake_bot()
    await run_promo_once(bot, temp_db_path)
    assert bot.copy_message.await_count == 1  # first post right away


async def test_stops_itself_after_duration_and_notifies_admins(temp_db_path, monkeypatch):
    import time
    from app.config import settings

    monkeypatch.setattr(settings, "admin_ids_raw", "42")
    await _ready_db(temp_db_path)
    await update_autopromo(temp_db_path, end_ts=int(time.time()) - 1, chat_title="Kanal")
    bot = _fake_bot()
    bot.send_message = AsyncMock()
    await run_promo_once(bot, temp_db_path)
    assert bot.copy_message.await_count == 0
    cfg = await get_autopromo(temp_db_path)
    assert cfg["enabled"] is False and cfg["end_ts"] == 0
    assert bot.send_message.await_args.args[0] == 42
    assert "tugadi" in bot.send_message.await_args.args[1]
    # stays stopped
    await run_promo_once(bot, temp_db_path)
    assert bot.send_message.await_count == 1


def _callback(data, message=None):
    cb = MagicMock()
    cb.data = data
    cb.from_user.id = 42
    cb.answer = AsyncMock()
    cb.message = message or MagicMock(edit_text=AsyncMock(), reply=AsyncMock())
    return cb


async def test_ad_message_asks_where_to_send(temp_db_path, monkeypatch):
    from app.config import settings
    from app.handlers import admin

    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")
    await init_db(temp_db_path)

    message = MagicMock()
    message.from_user.id = 42
    message.chat.id = 42
    message.message_id = 555
    message.video = object()
    message.video_note = None
    message.reply = AsyncMock()
    state = MagicMock(clear=AsyncMock())

    await admin.process_broadcast_message(message, state)

    cfg = await get_autopromo(temp_db_path)
    assert (cfg["src_chat_id"], cfg["src_message_id"], cfg["src_kind"]) == (42, 555, "video")
    message.copy_to.assert_not_called()  # nothing is sent to users yet
    markup = message.reply.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "bc:users" in datas and "promo:chat:w" in datas


async def test_broadcast_to_users_copies_saved_ad(temp_db_path, monkeypatch):
    from app.config import settings
    from app.db import upsert_user
    from app.handlers import admin

    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")
    await _ready_db(temp_db_path)
    await upsert_user(temp_db_path, 1)
    await upsert_user(temp_db_path, 2)
    cb = _callback("bc:users")
    cb.bot = _fake_bot()
    await admin.callback_broadcast_to_users(cb)
    assert cb.bot.copy_message.await_count == 2
    assert cb.bot.copy_message.await_args.kwargs["from_chat_id"] == 42


async def test_wizard_chat_interval_duration_then_starts(temp_db_path, monkeypatch):
    from app.config import settings
    from app.db import add_channel
    from app.handlers import admin

    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")
    await _ready_db(temp_db_path)
    await update_autopromo(temp_db_path, enabled=False, chat_id=None)
    await add_channel(temp_db_path, "-1005", "Homiy", "https://t.me/homiy")

    # step 1: chat picker lists sponsor channels with wizard suffix
    cb = _callback("promo:chat:w")
    await admin.callback_promo_chat(cb)
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    first = markup.inline_keyboard[0][0].callback_data
    assert first.startswith("promo:setchat:") and first.endswith(":w")

    # step 2: choosing chat leads to the interval picker (5 daqiqa available)
    cb = _callback(first)
    await admin.callback_promo_set_chat(cb)
    assert (await get_autopromo(temp_db_path))["chat_id"] == "-1005"
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "promo:setint:5:w" in datas

    # step 3: interval leads to the duration picker (5..10 soat available)
    cb = _callback("promo:setint:5:w")
    await admin.callback_promo_set_interval(cb)
    assert (await get_autopromo(temp_db_path))["interval_min"] == 5
    markup = cb.message.edit_text.await_args.kwargs["reply_markup"]
    datas = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert {"promo:setdur:5:w", "promo:setdur:8:w", "promo:setdur:10:w"} <= set(datas)

    # step 4: duration starts the auto-promo
    cb = _callback("promo:setdur:10:w")
    await admin.callback_promo_set_duration(cb)
    cfg = await get_autopromo(temp_db_path)
    assert cfg["enabled"] and cfg["duration_h"] == 10 and cfg["end_ts"] > 0 and cfg["last_sent_ts"] == 0
    shown = cb.message.edit_text.await_args.args[0]
    assert "Yoniq" in shown and "qoldi" in shown


async def test_menu_toggle_needs_chat_and_ad(temp_db_path, monkeypatch):
    from app.config import settings
    from app.handlers import admin

    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")
    await init_db(temp_db_path)
    cb = _callback("promo:toggle")
    await admin.callback_promo_toggle(cb)
    assert cb.answer.await_args.kwargs.get("show_alert") is True
    assert (await get_autopromo(temp_db_path))["enabled"] is False
