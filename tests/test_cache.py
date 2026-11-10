"""Unit tests for the SQLite cache layer."""

import os
import tempfile
import pytest
import pytest_asyncio
from app.db import init_db
from app.services.cache import (
    get_cache_by_url,
    get_cache_by_id,
    save_video_cache,
    save_audio_cache,
)


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.mark.asyncio
async def test_cache_video_lifecycle(temp_db_path: str) -> None:
    await init_db(temp_db_path)

    # 1. Not found initially
    entry = await get_cache_by_url(temp_db_path, "https://youtube.com/watch?v=123")
    assert entry is None

    # 2. Save video
    row_id = await save_video_cache(
        temp_db_path,
        url_key="https://youtube.com/watch?v=123",
        platform="YouTube",
        video_file_id="BAACAgIAAxkBAAIF...",
    )
    assert row_id > 0

    # 3. Retrieve by url
    cached = await get_cache_by_url(temp_db_path, "https://youtube.com/watch?v=123")
    assert cached is not None
    assert cached.id == row_id
    assert cached.platform == "YouTube"
    assert cached.video_file_id == "BAACAgIAAxkBAAIF..."
    assert cached.audio_file_id is None

    # 4. Retrieve by id
    by_id = await get_cache_by_id(temp_db_path, row_id)
    assert by_id is not None
    assert by_id.url_key == "https://youtube.com/watch?v=123"

    # 5. Save audio
    await save_audio_cache(temp_db_path, row_id, "CQACAgIAAxkBAAIX...")

    # 6. Verify audio is cached
    updated = await get_cache_by_id(temp_db_path, row_id)
    assert updated is not None
    assert updated.audio_file_id == "CQACAgIAAxkBAAIX..."
