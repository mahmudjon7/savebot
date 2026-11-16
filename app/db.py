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

CREATE TABLE IF NOT EXISTS join_requests (
    user_id     INTEGER NOT NULL,
    channel_id  TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS autopromo (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    enabled       INTEGER NOT NULL DEFAULT 0,
    chat_id       TEXT,
    chat_title    TEXT,
    interval_min  INTEGER NOT NULL DEFAULT 60,
    src_chat_id   INTEGER,
    src_message_id INTEGER,
    src_kind      TEXT,
    duration_h    INTEGER NOT NULL DEFAULT 10,
    end_ts        INTEGER NOT NULL DEFAULT 0,
    last_sent_ts  INTEGER NOT NULL DEFAULT 0,
    last_error    TEXT
);

CREATE TABLE IF NOT EXISTS referrals (
    invitee_id    INTEGER PRIMARY KEY,
    inviter_id    INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    confirmed_at  TEXT
);

CREATE INDEX IF NOT EXISTS idx_referrals_inviter ON referrals(inviter_id, status);
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


async def remove_channel_by_id(db_path: str, row_id: int) -> Optional[str]:
    """Remove a sponsor channel by its primary key ID and return its channel_id."""
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT channel_id FROM channels WHERE id = ?;", (row_id,)) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        await db.execute("DELETE FROM channels WHERE id = ?;", (row_id,))
        await db.commit()
        return str(row[0])


async def add_join_request(db_path: str, user_id: int, channel_ids: List[str]) -> None:
    """Record a pending channel join request for a user."""
    if not channel_ids:
        return
    sql = """
    INSERT INTO join_requests (user_id, channel_id, created_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(user_id, channel_id) DO UPDATE SET
        created_at = datetime('now');
    """
    async with aiosqlite.connect(db_path) as db:
        await db.executemany(sql, [(user_id, cid) for cid in channel_ids])
        await db.commit()


async def has_join_request(db_path: str, user_id: int, channel_ids: List[str]) -> bool:
    """Return True if the user has a recorded join request for any matching channel identifier."""
    if not channel_ids:
        return False
    placeholders = ", ".join("?" for _ in channel_ids)
    sql = f"SELECT 1 FROM join_requests WHERE user_id = ? AND channel_id IN ({placeholders}) LIMIT 1;"
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, (user_id, *channel_ids)) as cursor:
            return (await cursor.fetchone()) is not None


async def remove_join_request(db_path: str, user_id: int, channel_ids: List[str]) -> None:
    """Delete recorded join request(s) for a user in a channel."""
    if not channel_ids:
        return
    placeholders = ", ".join("?" for _ in channel_ids)
    sql = f"DELETE FROM join_requests WHERE user_id = ? AND channel_id IN ({placeholders});"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(sql, (user_id, *channel_ids))
        await db.commit()


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


# ---------------- AUTO-PROMO (single-chat self advertising) ----------------

_AUTOPROMO_FIELDS = {
    "enabled",
    "chat_id",
    "chat_title",
    "interval_min",
    "src_chat_id",
    "src_message_id",
    "src_kind",
    "duration_h",
    "end_ts",
    "last_sent_ts",
    "last_error",
}


async def get_autopromo(db_path: str) -> Dict[str, Any]:
    """Return the auto-promo settings row, creating the default row when missing."""
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO autopromo (id) VALUES (1);")
        await db.commit()
        async with db.execute(
            "SELECT enabled, chat_id, chat_title, interval_min, src_chat_id, src_message_id, src_kind, "
            "duration_h, end_ts, last_sent_ts, last_error "
            "FROM autopromo WHERE id = 1;"
        ) as cursor:
            row = await cursor.fetchone()
    return {
        "enabled": bool(row[0]),
        "chat_id": row[1],
        "chat_title": row[2],
        "interval_min": int(row[3]),
        "src_chat_id": row[4],
        "src_message_id": row[5],
        "src_kind": row[6],
        "duration_h": int(row[7]),
        "end_ts": int(row[8]),
        "last_sent_ts": int(row[9]),
        "last_error": row[10],
    }


async def update_autopromo(db_path: str, **fields: Any) -> None:
    """Update selected auto-promo settings (only known column names are accepted)."""
    unknown = set(fields) - _AUTOPROMO_FIELDS
    if unknown:
        raise ValueError(f"Unknown autopromo fields: {sorted(unknown)}")
    if not fields:
        return
    assignments = ", ".join(f"{name} = ?" for name in fields)
    values = [int(v) if isinstance(v, bool) else v for v in fields.values()]
    async with aiosqlite.connect(db_path) as db:
        await db.execute("INSERT OR IGNORE INTO autopromo (id) VALUES (1);")
        await db.execute(f"UPDATE autopromo SET {assignments} WHERE id = 1;", values)
        await db.commit()


# ---------------- REFERRALS (TAKLIF TIZIMI) ----------------

async def is_known_user(db_path: str, user_id: int) -> bool:
    """True if this Telegram user was ever seen: in users, in download history or as an invitee."""
    sql = """
    SELECT 1 WHERE EXISTS (SELECT 1 FROM users WHERE user_id = ?)
        OR EXISTS (SELECT 1 FROM downloads WHERE user_id = ?)
        OR EXISTS (SELECT 1 FROM referrals WHERE invitee_id = ?);
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, (user_id, user_id, user_id)) as cursor:
            return (await cursor.fetchone()) is not None


async def register_referral(db_path: str, inviter_id: int, invitee_id: int) -> bool:
    """Record a pending referral. Counts only real, different users; one record per invitee ever."""
    if inviter_id == invitee_id:
        return False
    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT 1 FROM users WHERE user_id = ?;", (inviter_id,)) as cursor:
            if (await cursor.fetchone()) is None:
                return False
        cursor = await db.execute(
            "INSERT OR IGNORE INTO referrals (invitee_id, inviter_id, status) VALUES (?, ?, 'pending');",
            (invitee_id, inviter_id),
        )
        await db.commit()
        return cursor.rowcount == 1


async def confirm_referral(db_path: str, invitee_id: int) -> Optional[int]:
    """Confirm the invitee's pending referral (once). Returns the inviter's ID only on the confirming call."""
    async with aiosqlite.connect(db_path) as db:
        cursor = await db.execute(
            "UPDATE referrals SET status = 'confirmed', confirmed_at = strftime('%Y-%m-%d %H:%M:%f', 'now') "
            "WHERE invitee_id = ? AND status = 'pending';",
            (invitee_id,),
        )
        await db.commit()
        if cursor.rowcount != 1:
            return None
        async with db.execute("SELECT inviter_id FROM referrals WHERE invitee_id = ?;", (invitee_id,)) as cur:
            row = await cur.fetchone()
            return int(row[0]) if row else None


async def get_referral_counts(db_path: str, inviter_id: int) -> Dict[str, int]:
    """Return confirmed and pending referral counts for one inviter."""
    sql = """
    SELECT
        COALESCE(SUM(CASE WHEN status = 'confirmed' THEN 1 ELSE 0 END), 0),
        COALESCE(SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END), 0)
    FROM referrals WHERE inviter_id = ?;
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql, (inviter_id,)) as cursor:
            row = await cursor.fetchone()
    return {"confirmed": int(row[0]), "pending": int(row[1])}


async def get_leaderboard(db_path: str) -> List[Dict[str, Any]]:
    """All inviters with at least one confirmed referral, best first (equal counts: who reached it earlier)."""
    sql = """
    SELECT r.inviter_id, COUNT(*) AS c, MAX(r.confirmed_at) AS reached_at, u.username
    FROM referrals r
    LEFT JOIN users u ON u.user_id = r.inviter_id
    WHERE r.status = 'confirmed'
    GROUP BY r.inviter_id
    ORDER BY c DESC, reached_at ASC, r.inviter_id ASC;
    """
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(sql) as cursor:
            rows = await cursor.fetchall()
    return [
        {"rank": i, "user_id": row[0], "count": int(row[1]), "username": row[3]}
        for i, row in enumerate(rows, start=1)
    ]

