"""Unit tests for sponsor channels, user cleanup, and subscription checking."""

import os
import tempfile
from datetime import datetime, timezone
import pytest
from unittest.mock import AsyncMock, MagicMock
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Chat, MessageOriginChannel
from app import texts
from app.config import settings
from app.db import (
    add_channel,
    add_join_request,
    get_all_user_ids,
    get_channels,
    get_stats_24h,
    has_join_request,
    init_db,
    remove_channel,
    remove_channel_by_id,
    remove_user,
    upsert_user,
)
from app.handlers.admin import callback_channels_list, process_channel_add
from app.handlers.start import callback_check_subscription
from app.services.subscription import (
    check_user_subscriptions,
    get_subscription_keyboard,
    normalize_channel_url,
    parse_channel_identifier,
)


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_user_management(temp_db_path: str) -> None:
    await init_db(temp_db_path)

    # Initially empty
    users = await get_all_user_ids(temp_db_path)
    assert users == []

    # Insert users
    await upsert_user(temp_db_path, user_id=111, username="alice")
    await upsert_user(temp_db_path, user_id=222, username="bob")

    users = await get_all_user_ids(temp_db_path)
    assert set(users) == {111, 222}

    # Remove user (e.g. if blocked)
    await remove_user(temp_db_path, user_id=111)
    users_after = await get_all_user_ids(temp_db_path)
    assert users_after == [222]


@pytest.mark.asyncio
async def test_channel_management(temp_db_path: str) -> None:
    await init_db(temp_db_path)

    # Empty channels
    channels = await get_channels(temp_db_path)
    assert channels == []

    # Add channel
    added = await add_channel(
        temp_db_path,
        channel_id="@mychannel",
        title="My Cool Channel",
        url="https://t.me/mychannel",
    )
    assert added is True

    # Retrieve channels
    channels = await get_channels(temp_db_path)
    assert len(channels) == 1
    assert channels[0]["channel_id"] == "@mychannel"
    assert channels[0]["title"] == "My Cool Channel"
    assert channels[0]["url"] == "https://t.me/mychannel"

    # Remove channel
    removed = await remove_channel(temp_db_path, "@mychannel")
    assert removed is True

    channels_after = await get_channels(temp_db_path)
    assert len(channels_after) == 0


@pytest.mark.asyncio
async def test_subscription_service_mocked(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    await add_channel(temp_db_path, "@ch1", "Channel 1", "https://t.me/ch1")
    await add_channel(temp_db_path, "@ch2", "Channel 2", "https://t.me/ch2")

    mock_bot = MagicMock()

    # User 1 is subscribed to ch1 (member), but not ch2 (left)
    async def fake_get_chat_member(chat_id, user_id):
        mock_member = MagicMock()
        if chat_id == "@ch1":
            mock_member.status = "member"
        else:
            mock_member.status = "left"
        return mock_member

    mock_bot.get_chat_member = AsyncMock(side_effect=fake_get_chat_member)

    is_sub, unsub = await check_user_subscriptions(mock_bot, user_id=999, db_path=temp_db_path)
    assert is_sub is False
    assert len(unsub) == 1
    assert unsub[0]["channel_id"] == "@ch2"

    # Generate keyboard
    markup = get_subscription_keyboard(unsub)
    assert len(markup.inline_keyboard) == 2  # 1 channel button + 1 verify button
    assert markup.inline_keyboard[1][0].callback_data == "sub:check"


def test_parse_channel_identifier_and_url_normalization() -> None:
    assert parse_channel_identifier("@mychannel") == ("@mychannel", None)
    assert parse_channel_identifier("mychannel") == ("@mychannel", None)
    assert parse_channel_identifier("https://t.me/mychannel") == ("@mychannel", None)
    assert parse_channel_identifier("t.me/mychannel/42") == ("@mychannel", None)
    assert parse_channel_identifier("-1001234567890") == (-1001234567890, None)
    assert parse_channel_identifier("https://t.me/c/1234567890/5") == (-1001234567890, None)

    lookup, invite = parse_channel_identifier("https://t.me/+AbCdEf123")
    assert lookup is None
    assert invite == "https://t.me/+AbCdEf123"

    lookup2, invite2 = parse_channel_identifier("t.me/joinchat/XYZ")
    assert lookup2 is None
    assert invite2 == "https://t.me/joinchat/XYZ"

    assert normalize_channel_url("t.me/mychannel") == "https://t.me/mychannel"
    assert normalize_channel_url("@mychannel") == "https://t.me/mychannel"
    assert normalize_channel_url("https://t.me/-1001234567890", "-1001234567890") is None
    assert normalize_channel_url("https://t.me/-1001234567890", "@fallback") == "https://t.me/fallback"
    assert normalize_channel_url("https://t.me/https://t.me/bad", "bad") == "https://t.me/bad"


@pytest.mark.asyncio
async def test_subscription_normalizes_legacy_and_restricted_and_join_requests(temp_db_path: str) -> None:
    await init_db(temp_db_path)
    await add_channel(temp_db_path, "https://t.me/legacych", "Legacy", "https://t.me/legacych")
    await add_channel(temp_db_path, "-100999888777", "Private", "https://t.me/+priv")

    seen_chat_ids = []

    async def fake_get_chat_member(chat_id, user_id):
        seen_chat_ids.append(chat_id)
        member = MagicMock()
        if chat_id == "@legacych":
            member.status = "restricted"
            member.is_member = False
        else:
            member.status = "left"
        return member

    mock_bot = MagicMock()
    mock_bot.get_chat_member = AsyncMock(side_effect=fake_get_chat_member)

    is_sub, unsub = await check_user_subscriptions(mock_bot, user_id=555, db_path=temp_db_path)
    assert is_sub is False
    assert len(unsub) == 2
    assert "@legacych" in seen_chat_ids
    assert -100999888777 in seen_chat_ids

    # Simulate pending join request for private channel + restricted is_member=True for legacy
    await add_join_request(temp_db_path, user_id=555, channel_ids=["-100999888777"])

    async def fake_get_chat_member_after(chat_id, user_id):
        member = MagicMock()
        if chat_id == "@legacych":
            member.status = "restricted"
            member.is_member = True
        else:
            member.status = "left"
        return member

    mock_bot.get_chat_member = AsyncMock(side_effect=fake_get_chat_member_after)
    is_sub2, unsub2 = await check_user_subscriptions(mock_bot, user_id=555, db_path=temp_db_path)
    assert is_sub2 is True
    assert unsub2 == []

    # Once approved to member, join_request row should be cleaned up so leaving later blocks again
    async def fake_member_approved(chat_id, user_id):
        member = MagicMock()
        member.status = "member"
        return member

    mock_bot.get_chat_member = AsyncMock(side_effect=fake_member_approved)
    is_sub3, _ = await check_user_subscriptions(mock_bot, user_id=555, db_path=temp_db_path)
    assert is_sub3 is True
    assert await has_join_request(temp_db_path, 555, ["-100999888777"]) is False


@pytest.mark.asyncio
async def test_subscription_keyboard_skips_invalid_urls() -> None:
    unsub = [
        {"channel_id": "-100123", "title": "Broken", "url": "https://t.me/-100123"},
        {"channel_id": "-100456", "title": "Valid", "url": "https://t.me/+abc"},
    ]
    markup = get_subscription_keyboard(unsub)
    assert len(markup.inline_keyboard) == 2
    assert markup.inline_keyboard[0][0].url == "https://t.me/+abc"
    assert markup.inline_keyboard[1][0].callback_data == "sub:check"


@pytest.mark.asyncio
async def test_admin_process_channel_add_verifies_bot_admin_and_formats(
    temp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await init_db(temp_db_path)
    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")

    state = MagicMock()
    state.clear = AsyncMock()

    # 1. Invite link alone is rejected without clearing state
    msg_invite = MagicMock()
    msg_invite.from_user = MagicMock(id=42)
    msg_invite.forward_origin = None
    msg_invite.forward_from_chat = None
    msg_invite.text = "https://t.me/+OnlyInvite"
    msg_invite.reply = AsyncMock()
    await process_channel_add(msg_invite, state)
    assert await get_channels(temp_db_path) == []
    state.clear.assert_not_called()

    # 2. Public channel link where bot is NOT admin is rejected
    bot_not_admin = MagicMock()
    bot_not_admin.id = 999
    bot_not_admin.get_chat = AsyncMock(
        return_value=MagicMock(id=-100111, type="channel", title="Sponsor", username="sponsor_ch")
    )
    bot_not_admin.get_chat_member = AsyncMock(return_value=MagicMock(status="member"))

    msg_not_admin = MagicMock()
    msg_not_admin.from_user = MagicMock(id=42)
    msg_not_admin.forward_origin = None
    msg_not_admin.forward_from_chat = None
    msg_not_admin.text = "https://t.me/sponsor_ch"
    msg_not_admin.bot = bot_not_admin
    msg_not_admin.reply = AsyncMock()
    await process_channel_add(msg_not_admin, state)
    assert await get_channels(temp_db_path) == []
    msg_not_admin.reply.assert_awaited_once()
    assert texts.CHANNEL_ADD_NOT_ADMIN in msg_not_admin.reply.call_args.args[0]

    # 3. Forwarded private channel post where bot IS admin succeeds using invite link
    bot_admin = MagicMock()
    bot_admin.id = 999
    bot_admin.get_chat = AsyncMock(
        return_value=MagicMock(
            id=-100222,
            type="channel",
            title="Private <Sponsor>",
            username=None,
            invite_link="https://t.me/+PrivateJoin",
        )
    )
    bot_admin.get_chat_member = AsyncMock(return_value=MagicMock(status="administrator"))

    fwd_chat = Chat(id=-100222, type="channel", title="Private <Sponsor>")
    msg_fwd = MagicMock()
    msg_fwd.from_user = MagicMock(id=42)
    msg_fwd.forward_origin = MessageOriginChannel(
        date=datetime.now(timezone.utc),
        chat=fwd_chat,
        message_id=10,
    )
    msg_fwd.text = None
    msg_fwd.bot = bot_admin
    msg_fwd.reply = AsyncMock()

    await process_channel_add(msg_fwd, state)
    channels = await get_channels(temp_db_path)
    assert len(channels) == 1
    assert channels[0]["channel_id"] == "-100222"
    assert channels[0]["url"] == "https://t.me/+PrivateJoin"
    state.clear.assert_awaited_once()

    # Delete by row ID works too
    removed = await remove_channel_by_id(temp_db_path, channels[0]["id"])
    assert removed == "-100222"
    assert await get_channels(temp_db_path) == []


@pytest.mark.asyncio
async def test_callback_check_sub_ignores_message_not_modified_and_channels_back_clears_state(
    temp_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    await init_db(temp_db_path)
    await add_channel(temp_db_path, "@ch1", "Channel 1", "https://t.me/ch1")
    monkeypatch.setattr(settings, "db_path", temp_db_path)
    monkeypatch.setattr(settings, "admin_ids_raw", "42")

    mock_bot = MagicMock()
    mock_bot.get_chat_member = AsyncMock(return_value=MagicMock(status="left"))

    callback = MagicMock()
    callback.from_user = MagicMock(id=777)
    callback.bot = mock_bot
    callback.answer = AsyncMock()
    callback.message = MagicMock()
    callback.message.edit_reply_markup = AsyncMock(
        side_effect=TelegramBadRequest(method=MagicMock(), message="Bad Request: message is not modified")
    )

    # Should not raise TelegramBadRequest
    await callback_check_subscription(callback)
    callback.answer.assert_awaited_once_with(texts.SUB_CHECK_FAIL, show_alert=True)

    # Clicking back to channels list clears FSM state
    admin_cb = MagicMock()
    admin_cb.from_user = MagicMock(id=42)
    admin_cb.message = MagicMock()
    admin_cb.message.edit_text = AsyncMock()
    admin_cb.answer = AsyncMock()
    state = MagicMock()
    state.clear = AsyncMock()
    await callback_channels_list(admin_cb, state)
    state.clear.assert_awaited_once()
