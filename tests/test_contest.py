"""Tests for the referral contest: participation, counting window, qualification, draw, admin control."""

import os
import random
import tempfile
from unittest.mock import AsyncMock, MagicMock

import aiosqlite
import pytest

from app.config import settings
from app.db import confirm_referral, init_db, record_download, register_referral, upsert_user
from app.services import contest as ct
from app.services.referral import referral_menu_keyboard


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    for suffix in ("", "-wal", "-shm"):
        if os.path.exists(path + suffix):
            os.remove(path + suffix)


async def _invite(db_path, inviter, count, base):
    """Make `count` brand-new users join via `inviter` and pass the subscription check."""
    for i in range(count):
        invitee = base + i
        assert await register_referral(db_path, inviter, invitee)
        assert await confirm_referral(db_path, invitee) == inviter


async def _player(db_path, uid, invites, base, downloads=1):
    await upsert_user(db_path, uid, f"u{uid}")
    await ct.join_contest(db_path, uid)
    if downloads:
        await record_download(db_path, uid, "https://tiktok.com/x", "ok")
    await _invite(db_path, uid, invites, base)


async def _running(db_path, min_invites=3, winners=3):
    await init_db(db_path)
    await ct.update_settings(db_path, min_invites=min_invites, winners_count=winners)
    await ct.start_contest(db_path)


async def test_join_only_while_contest_is_running(db_path):
    await init_db(db_path)
    assert await ct.join_contest(db_path, 1) is False            # contest never started
    await ct.start_contest(db_path)
    assert await ct.join_contest(db_path, 1) is True
    assert await ct.join_contest(db_path, 1) is False            # already in
    assert (await ct.get_contest(db_path))["members"] == 1
    await ct.cancel_contest(db_path)
    assert await ct.join_contest(db_path, 2) is False


async def test_only_confirmed_invites_inside_the_window_count(db_path):
    await _running(db_path)
    await upsert_user(db_path, 1, "a")
    await ct.join_contest(db_path, 1)
    await _invite(db_path, 1, 2, base=100)
    assert await register_referral(db_path, 1, 200)              # pending: not confirmed yet
    async with aiosqlite.connect(db_path) as db:                 # an old invite made before the contest
        await db.execute(
            "UPDATE referrals SET confirmed_at = '2000-01-01 00:00:00.000' WHERE invitee_id = 100;"
        )
        await db.commit()
    standings = await ct.get_standings(db_path)
    assert standings[0]["invites"] == 1


async def test_invites_of_non_participants_do_not_show_up(db_path):
    await _running(db_path)
    await upsert_user(db_path, 1, "a")
    await _invite(db_path, 1, 3, base=100)                       # never pressed "join"
    assert await ct.get_standings(db_path) == []


async def test_qualification_needs_invites_and_a_downloaded_video(db_path):
    await _running(db_path, min_invites=3)
    await _player(db_path, 1, invites=3, base=100, downloads=0)  # enough invites, no video
    await _player(db_path, 2, invites=2, base=200)               # video, too few invites
    await _player(db_path, 3, invites=3, base=300)
    rows = {r["user_id"]: r for r in await ct.get_standings(db_path)}
    assert [uid for uid, r in rows.items() if ct.is_qualified(r, 3)] == [3]


async def test_draw_top_inviter_first_others_random_among_qualified(db_path):
    await _running(db_path, min_invites=3, winners=3)
    await _player(db_path, 1, invites=6, base=100)
    for uid in (2, 3, 4, 5):
        await _player(db_path, uid, invites=3, base=uid * 100)
    await _player(db_path, 9, invites=2, base=900)               # not qualified: can never win
    winners = await ct.finish_contest(db_path, random.Random(1))
    assert [w["user_id"] for w in winners][0] == 1
    assert winners[0]["kind"] == "top" and winners[0]["place"] == 1
    assert len(winners) == 3
    assert {w["user_id"] for w in winners} <= {1, 2, 3, 4, 5}
    assert len({w["user_id"] for w in winners}) == 3
    assert (await ct.get_contest(db_path))["status"] == "ended"
    assert await ct.finish_contest(db_path) is None              # cannot finish twice


async def test_fewer_qualified_than_prizes(db_path):
    await _running(db_path, min_invites=3, winners=3)
    await _player(db_path, 1, invites=3, base=100)
    winners = await ct.finish_contest(db_path)
    assert [w["user_id"] for w in winners] == [1]


async def test_nobody_qualified_means_no_winners(db_path):
    await _running(db_path, min_invites=5)
    await _player(db_path, 1, invites=2, base=100)
    assert await ct.finish_contest(db_path) == []
    assert (await ct.get_contest(db_path))["status"] == "ended"


async def test_disqualified_winner_is_replaced(db_path):
    await _running(db_path, min_invites=3, winners=2)
    await _player(db_path, 1, invites=6, base=100)
    await _player(db_path, 2, invites=4, base=200)
    await _player(db_path, 3, invites=3, base=300)
    await ct.finish_contest(db_path, random.Random(0))

    replacement = await ct.disqualify(db_path, 1)                # the top inviter was cheating
    assert replacement["user_id"] in (2, 3)
    winners = await ct.get_winners(db_path)
    assert 1 not in {w["user_id"] for w in winners}
    assert len(winners) == 2
    assert next(w for w in winners if w["place"] == 1)["kind"] == "top"
    assert (await ct.get_member(db_path, 1))["disqualified"] is True


async def test_disqualify_without_replacement_leaves_fewer_winners(db_path):
    await _running(db_path, min_invites=3, winners=3)
    await _player(db_path, 1, invites=3, base=100)
    await ct.finish_contest(db_path)
    assert await ct.disqualify(db_path, 1) is None
    assert await ct.get_winners(db_path) == []


async def test_notify_winners_once(db_path):
    await _running(db_path, min_invites=3, winners=2)
    await _player(db_path, 1, invites=3, base=100)
    await _player(db_path, 2, invites=3, base=200)
    await ct.finish_contest(db_path)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    assert await ct.notify_winners(bot, db_path) == 2
    assert await ct.notify_winners(bot, db_path) == 0
    assert bot.send_message.await_count == 2


async def test_scheduler_finishes_expired_contest_and_tells_admins(db_path, monkeypatch):
    await _running(db_path, min_invites=3)
    await _player(db_path, 1, invites=3, base=100)
    bot = MagicMock()
    bot.send_message = AsyncMock()
    monkeypatch.setattr(settings, "admin_ids_raw", "777")

    assert await ct.run_contest_once(bot, db_path) is False      # still running, not due
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE contest SET ends_at = '2000-01-01 00:00:00.000' WHERE id = 1;")
        await db.commit()
    assert await ct.run_contest_once(bot, db_path) is True
    assert (await ct.get_contest(db_path))["status"] == "ended"
    assert bot.send_message.await_args.args[0] == 777
    assert await ct.run_contest_once(bot, db_path) is False      # only once


async def test_expired_contest_is_not_active_and_blocks_joining(db_path):
    await _running(db_path)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("UPDATE contest SET ends_at = '2000-01-01 00:00:00.000' WHERE id = 1;")
        await db.commit()
    assert (await ct.get_contest(db_path))["active"] is False
    assert await ct.join_contest(db_path, 5) is False


async def test_starting_again_clears_previous_participants_and_winners(db_path):
    await _running(db_path, min_invites=3)
    await _player(db_path, 1, invites=3, base=100)
    await ct.finish_contest(db_path)
    await ct.start_contest(db_path)
    assert await ct.get_winners(db_path) == []
    assert (await ct.get_contest(db_path))["members"] == 0


async def test_contest_button_only_while_active():
    def callbacks(markup):
        return [b.callback_data for row in markup.inline_keyboard for b in row]

    assert "ct:me" not in callbacks(referral_menu_keyboard())
    assert "ct:me" in callbacks(referral_menu_keyboard(True))


async def test_user_screen_states(db_path):
    from app.handlers.contest import render_user_contest

    bot = MagicMock()
    bot.me = AsyncMock(return_value=MagicMock(username="my_bot"))
    await init_db(db_path)
    text, markup = await render_user_contest(bot, db_path, 1)
    assert "faol konkurs yo'q" in text

    await ct.update_settings(db_path, min_invites=3)
    await ct.start_contest(db_path)
    text, markup = await render_user_contest(bot, db_path, 1)
    assert "ct:join" in [b.callback_data for row in markup.inline_keyboard for b in row]

    await upsert_user(db_path, 1, "a")
    await ct.join_contest(db_path, 1)
    text, markup = await render_user_contest(bot, db_path, 1)
    assert "0</b> / 3" in text and "video yuklab oling" in text   # joined, no download yet
    assert "start=ref_1" in text


async def test_user_screen_shows_friends_waiting_for_subscription(db_path):
    from app.handlers.contest import render_user_contest

    bot = MagicMock()
    bot.me = AsyncMock(return_value=MagicMock(username="my_bot"))
    await _running(db_path, min_invites=3)
    await _player(db_path, 1, invites=1, base=100)
    assert await register_referral(db_path, 1, 500)               # started the bot, not subscribed yet
    text, _ = await render_user_contest(bot, db_path, 1)
    assert "1</b> / 3" in text
    assert "Kutilayotgan do'stlar: <b>1</b>" in text


def _start_message(user_id=70):
    m = MagicMock()
    m.from_user.id = user_id
    m.from_user.username = "newbie"
    m.chat.type = "private"
    m.bot.me = AsyncMock(return_value=MagicMock(username="my_bot"))
    m.bot.send_message = AsyncMock()
    m.answer = AsyncMock()
    return m


async def _do_start(db_path, monkeypatch, args):
    from aiogram.filters import CommandObject
    from app.handlers import start

    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(start, "check_user_subscriptions", AsyncMock(return_value=(True, [])))
    msg = _start_message()
    state = MagicMock()
    state.clear = AsyncMock()
    await start.handle_start(msg, state, CommandObject(command="start", args=args))
    return msg


async def test_contest_button_opens_bot_and_explains_the_rules(db_path, monkeypatch):
    await _running(db_path, min_invites=3)
    msg = await _do_start(db_path, monkeypatch, "konkurs")
    text = msg.answer.await_args.args[0]
    assert "KONKURS" in text and "Qanday qatnashiladi" in text
    buttons = [b.callback_data for row in msg.answer.await_args.kwargs["reply_markup"].inline_keyboard for b in row]
    assert "ct:join" in buttons


async def test_contest_link_without_active_contest_shows_normal_welcome(db_path, monkeypatch):
    await init_db(db_path)
    msg = await _do_start(db_path, monkeypatch, "konkurs")
    assert "KONKURS" not in msg.answer.await_args.args[0]


async def test_announcement_reaches_users_with_join_button_and_drops_blocked(db_path):
    from aiogram.exceptions import TelegramForbiddenError

    await _running(db_path)
    for uid in (1, 2, 3):
        await upsert_user(db_path, uid, f"u{uid}")
    bot = MagicMock()
    bot.me = AsyncMock(return_value=MagicMock(username="my_bot"))

    async def send(uid, text, **kw):
        if uid == 2:
            raise TelegramForbiddenError(method=MagicMock(), message="blocked")

    bot.send_message = AsyncMock(side_effect=send)
    result = await ct.broadcast_announcement(bot, db_path, "hello")
    assert result == {"sent": 2, "blocked": 1}
    markup = bot.send_message.await_args.kwargs["reply_markup"]
    assert markup.inline_keyboard[0][0].url == "https://t.me/my_bot?start=konkurs"
    from app.db import get_all_user_ids
    assert sorted(await get_all_user_ids(db_path)) == [1, 3]
