"""Tests for the referral system (accurate counting, TOP list) and video branding."""

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db import (
    add_channel,
    confirm_referral,
    get_leaderboard,
    get_referral_counts,
    init_db,
    is_known_user,
    record_download,
    register_referral,
    upsert_user,
)
from app.services.referral import (
    confirm_and_notify,
    make_ref_link,
    parse_ref_payload,
    render_my_referrals,
    render_top,
    share_url,
    video_branding,
)


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


def _bot(username="my_bot"):
    bot = MagicMock()
    bot.me = AsyncMock(return_value=MagicMock(username=username))
    bot.send_message = AsyncMock()
    return bot


def test_parse_ref_payload():
    assert parse_ref_payload("ref_12345") == 12345
    for bad in (None, "", "ref_", "ref_abc", "ref_-5", "ref_12 34", "promo_5", "ref_" + "9" * 30):
        assert parse_ref_payload(bad) is None


async def test_register_rules(db_path):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    assert await register_referral(db_path, 1, 1) is False          # not yourself
    assert await register_referral(db_path, 999, 2) is False        # inviter is not a bot user
    assert await register_referral(db_path, 1, 2) is True
    assert await register_referral(db_path, 1, 2) is False         # same invitee twice
    await upsert_user(db_path, 3, "bob")
    assert await register_referral(db_path, 3, 2) is False         # invitee already belongs to alice


async def test_is_known_user_sees_users_downloads_and_invitees(db_path):
    await init_db(db_path)
    assert await is_known_user(db_path, 10) is False
    await upsert_user(db_path, 10)
    assert await is_known_user(db_path, 10) is True
    await record_download(db_path, 11, "u", "ok")                   # blocked the bot later, but used it
    assert await is_known_user(db_path, 11) is True
    await upsert_user(db_path, 1)
    await register_referral(db_path, 1, 12)
    assert await is_known_user(db_path, 12) is True


async def test_pending_does_not_count_until_confirmed_once(db_path):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    await upsert_user(db_path, 2)
    await register_referral(db_path, 1, 2)
    assert await get_referral_counts(db_path, 1) == {"confirmed": 0, "pending": 1}
    assert await get_leaderboard(db_path) == []
    assert await confirm_referral(db_path, 2) == 1
    assert await confirm_referral(db_path, 2) is None               # second confirm does nothing
    assert await confirm_referral(db_path, 777) is None             # no referral at all
    assert await get_referral_counts(db_path, 1) == {"confirmed": 1, "pending": 0}


async def test_inviter_is_notified_exactly_once(db_path):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    await upsert_user(db_path, 2)
    await register_referral(db_path, 1, 2)
    bot = _bot()
    assert await confirm_and_notify(bot, db_path, 2) is True
    assert await confirm_and_notify(bot, db_path, 2) is False
    assert bot.send_message.await_count == 1
    assert bot.send_message.await_args.args[0] == 1
    assert "<b>1</b>" in bot.send_message.await_args.args[1]
    # inviter blocked the bot: still no crash and the referral stays confirmed
    await upsert_user(db_path, 3)
    await register_referral(db_path, 1, 3)
    bot.send_message.side_effect = RuntimeError("Forbidden")
    assert await confirm_and_notify(bot, db_path, 3) is True
    assert (await get_referral_counts(db_path, 1))["confirmed"] == 2


async def test_leaderboard_order_ranks_and_texts(db_path):
    await init_db(db_path)
    for uid, name in [(1, "alice"), (2, "bob"), (3, None)]:
        await upsert_user(db_path, uid, name)
    invitee = 100
    for inviter, how_many in [(2, 2), (1, 1), (3, 2)]:
        for _ in range(how_many):
            invitee += 1
            await upsert_user(db_path, invitee)
            await register_referral(db_path, inviter, invitee)
            await confirm_referral(db_path, invitee)
    board = await get_leaderboard(db_path)
    assert [(r["user_id"], r["count"], r["rank"]) for r in board] == [(2, 2, 1), (3, 2, 2), (1, 1, 3)]  # tie: earlier first
    top = await render_top(db_path, 1)
    assert "@bob" in top and "Foydalanuvchi …3" in top and "@alice" in top
    assert "Sizning o'rningiz: <b>3</b>" in top
    assert "hali hech kimni" in await render_top(db_path, 555)
    text, markup = await render_my_referrals(_bot(), db_path, 2)
    assert "https://t.me/my_bot?start=ref_2" in text
    assert "<b>1</b>" in text  # rank 1


async def test_empty_top(db_path):
    await init_db(db_path)
    assert "Birinchi bo'ling" in await render_top(db_path, 1)


async def test_video_branding_caption_and_share_button():
    caption, markup = await video_branding(_bot(), 42, "TikTok <b>")
    assert caption.startswith("TikTok &lt;b&gt;")
    assert "📥 @my_bot orqali yuklandi" in caption
    url = markup.inline_keyboard[0][0].url
    assert url == share_url(make_ref_link("my_bot", 42))
    assert "start%3Dref_42" in url and url.startswith("https://t.me/share/url?url=")
    caption, markup = await video_branding(_bot(username=""), 42, None)
    assert caption == "Video" and markup is None


def _message(user_id=50, username="newbie"):
    m = MagicMock()
    m.from_user.id = user_id
    m.from_user.username = username
    m.bot = _bot()
    m.answer = AsyncMock()
    return m


async def _start(db_path, monkeypatch, message, args, subscribed=True):
    from app.config import settings
    from app.handlers import start

    monkeypatch.setattr(settings, "db_path", db_path)
    monkeypatch.setattr(
        start, "check_user_subscriptions", AsyncMock(return_value=(subscribed, [] if subscribed else [{"id": 1}]))
    )
    monkeypatch.setattr(start, "get_subscription_keyboard", lambda unsub: None)
    state = MagicMock(clear=AsyncMock())
    await start.handle_start(message, state, MagicMock(args=args))


async def test_start_flow_new_user_with_sponsors_confirms_after_subscription(db_path, monkeypatch):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    msg = _message()
    await _start(db_path, monkeypatch, msg, "ref_1", subscribed=False)
    assert await get_referral_counts(db_path, 1) == {"confirmed": 0, "pending": 1}
    await _start(db_path, monkeypatch, _message(), "ref_1", subscribed=True)  # second /start: already known, no 2nd record
    assert await get_referral_counts(db_path, 1) == {"confirmed": 1, "pending": 0}  # confirmed as sub passed


async def test_start_flow_existing_user_and_self_are_not_counted(db_path, monkeypatch):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    await upsert_user(db_path, 60, "old_user")
    await _start(db_path, monkeypatch, _message(user_id=60), "ref_1")   # already a user
    await _start(db_path, monkeypatch, _message(user_id=1), "ref_1")    # own link
    await _start(db_path, monkeypatch, _message(user_id=61), "ref_999") # unknown inviter
    assert await get_referral_counts(db_path, 1) == {"confirmed": 0, "pending": 0}
    assert await get_leaderboard(db_path) == []


async def test_start_flow_new_user_without_sponsors_counts_immediately(db_path, monkeypatch):
    await init_db(db_path)
    await upsert_user(db_path, 1, "alice")
    msg = _message(user_id=70)
    await _start(db_path, monkeypatch, msg, "ref_1")
    assert await get_referral_counts(db_path, 1) == {"confirmed": 1, "pending": 0}
    assert msg.answer.await_args.kwargs["reply_markup"] is not None  # welcome has invite/TOP buttons


async def test_stats_separate_rejected_links_from_real_failures(db_path):
    from app.db import get_stats_24h

    await init_db(db_path)
    await record_download(db_path, 1, "https://t.me/shop", "rejected", "Domain not in allowed platforms")
    await record_download(db_path, 1, "https://t.me/old", "failed", "Domain not in allowed platforms")  # old rows
    await record_download(db_path, 1, "https://tiktok.com/x", "failed", "timeout")
    await record_download(db_path, 1, "https://tiktok.com/y", "blocked", "content:adult")
    await record_download(db_path, 1, "https://tiktok.com/z", "ok")
    stats = await get_stats_24h(db_path)
    assert stats["total_downloads"] == 5
    assert stats["failures"] == 1      # only the real timeout
    assert stats["rejected"] == 2
    assert stats["blocked"] == 1
