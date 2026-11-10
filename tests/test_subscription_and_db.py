"""Unit tests for sponsor channels, user cleanup, and subscription checking."""

import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.db import (
    add_channel,
    get_all_user_ids,
    get_channels,
    get_stats_24h,
    init_db,
    remove_channel,
    remove_user,
    upsert_user,
)
from app.services.subscription import check_user_subscriptions, get_subscription_keyboard


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
