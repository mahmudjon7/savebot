"""SQLite database operations using aiosqlite."""

import os
from typing import Any, Dict, List, Optional
import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_seen  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  TEXT NOT NULL UNIQUE,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url_key         TEXT NOT NULL UNIQUE,
    platform        TEXT,
    video_file_id   TEXT,
    audio_file_id   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    url_key     TEXT NOT NULL,
    status      TEXT NOT NULL,
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_media_cache_url_key ON media_cache(url_key);
CREATE INDEX IF NOT EXISTS idx_downloads_created_at ON downloads(created_at);
"""


async def init_db(db_path: str) -> None:
    """Initialize database and create schema tables."""
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(db_path) as db:
        await db.executescript(SCHEMA_SQL)
        await db.commit()


async def upsert_user(db_path: str, user_id: int, username: Optional[str] = None) -> None:
    """Insert or update a user's record with last seen timestamp."""
    sql = """
    INSERT INTO users (user_id, username, first_seen, last_seen)
    VALUES (?, ?, datetime('now'), datetime('now'))
    ON CONFLICT(user_id) DO UPDATE SET
        username = excluded.username,
        last_seen = datetime('now');
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (user_id, username))
        await db.commit()


async def get_all_user_ids(db_path: str) -> List[int]:
    """Retrieve all user IDs for broadcasting."""
    sql = "SELECT user_id FROM users;"
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]


async def remove_user(db_path: str, user_id: int) -> None:
    """Remove user from database (e.g., if user blocked the bot)."""
    sql = "DELETE FROM users WHERE user_id = ?;"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (user_id,))
        await db.commit()


async def add_channel(db_path: str, channel_id: str, title: str, url: str) -> bool:
    """Add a sponsor channel for mandatory subscription."""
    sql = """
    INSERT INTO channels (channel_id, title, url, created_at)
    VALUES (?, ?, ?, datetime('now'))
    ON CONFLICT(channel_id) DO UPDATE SET
        title = excluded.title,
        url = excluded.url;
    """
    try:
        async with aiosqlite.connect(db_path) as db:
            await db.execute(sql, (str(channel_id), title, url))
            await db.commit()
            return True
    except Exception:
        return False


async def remove_channel(db_path: str, channel_id: str) -> bool:
    """Remove a sponsor channel."""
    sql = "DELETE FROM channels WHERE channel_id = ?;"
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(sql, (str(channel_id),))
        await db.commit()
        return cursor.rowcount > 0


async def get_channels(db_path: str) -> List[Dict[str, Any]]:
    """Retrieve all sponsor channels."""
    sql = "SELECT id, channel_id, title, url, created_at FROM channels ORDER BY id ASC;"
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
            return [
                {
                    "id": row[0],
                    "channel_id": row[1],
                    "title": row[2],
                    "url": row[3],
                    "created_at": row[4],
                }
                for row in rows
            ]


async def record_download(
    db_path: str,
    user_id: int,
    url_key: str,
    status: str,
    error: Optional[str] = None,
) -> None:
    """Record a download attempt into the downloads table."""
    sql = """
    INSERT INTO downloads (user_id, url_key, status, error, created_at)
    VALUES (?, ?, ?, ?, datetime('now'));
    """
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (user_id, url_key, status, error))
        await db.commit()


async def get_stats_24h(db_path: str) -> Dict[str, Any]:
    """Calculate usage statistics for the last 24 hours."""
    async with aiosqlite.connect(db_path) as db:
        # Total registered users
        async with db.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            total_users = row[0] if row else 0

        # Total channels
        async with db.execute("SELECT COUNT(*) FROM channels") as cursor:
            row = await cursor.fetchone()
            total_channels = row[0] if row else 0

        # Downloads in the last 24h
        sql_24h = """
        SELECT
            COUNT(*),
            SUM(CASE WHEN status = 'cache_hit' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END)
        FROM downloads
        WHERE created_at >= datetime('now', '-1 day');
        """
        async with db.execute(sql_24h) as cursor:
            row = await cursor.fetchone()
            total_downloads = row[0] if row and row[0] else 0
            cache_hits = row[1] if row and row[1] else 0
            failures = row[2] if row and row[2] else 0

    hit_rate = (cache_hits / total_downloads * 100) if total_downloads > 0 else 0.0

    return {
        "total_users": total_users,
        "total_channels": total_channels,
        "total_downloads": total_downloads,
        "cache_hits": cache_hits,
        "failures": failures,
        "hit_rate": hit_rate,
    }
