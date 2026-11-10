"""Cache service for storing and retrieving Telegram file_ids."""

from dataclasses import dataclass
from typing import Optional
import aiosqlite


@dataclass
class CacheEntry:
    """Cached media record representing a normalized URL."""

    id: int
    url_key: str
    platform: Optional[str]
    video_file_id: Optional[str]
    audio_file_id: Optional[str]
    created_at: str


async def get_cache_by_url(db_path: str, url_key: str) -> Optional[CacheEntry]:
    """Fetch cache entry by normalized url_key."""
    sql = """
    SELECT id, url_key, platform, video_file_id, audio_file_id, created_at
    FROM media_cache
    WHERE url_key = ?
    LIMIT 1;
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, (url_key,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return CacheEntry(*row)
    return None


async def get_cache_by_id(db_path: str, row_id: int) -> Optional[CacheEntry]:
    """Fetch cache entry by primary key ID."""
    sql = """
    SELECT id, url_key, platform, video_file_id, audio_file_id, created_at
    FROM media_cache
    WHERE id = ?
    LIMIT 1;
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, (row_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return CacheEntry(*row)
    return None


async def save_video_cache(
    db_path: str,
    url_key: str,
    platform: Optional[str],
    video_file_id: str,
) -> int:
    """Insert or update video cache and return the row ID."""
    sql = """
    INSERT INTO media_cache (url_key, platform, video_file_id, created_at)
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT(url_key) DO UPDATE SET
        platform = excluded.platform,
        video_file_id = excluded.video_file_id;
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (url_key, platform, video_file_id))
        await db.commit()

        # Retrieve the row ID
        async with db.execute("SELECT id FROM media_cache WHERE url_key = ?", (url_key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0


async def save_audio_cache(
    db_path: str,
    row_id: int,
    audio_file_id: str,
) -> None:
    """Save audio file_id to existing cache entry by ID."""
    sql = "UPDATE media_cache SET audio_file_id = ? WHERE id = ?;"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (audio_file_id, row_id))
        await db.commit()
