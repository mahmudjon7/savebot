# savebot
# 🎬 ClipGrab Bot

> A fast, minimal Telegram bot that turns a link into a video. Send a TikTok, Instagram Reels or YouTube Shorts URL and get the video back in seconds, playable inline, no watermarks to fight with, no ads.

Built with **Python 3.12**, **aiogram 3**, **yt-dlp** and **ffmpeg**. Runs in Docker, deploys to any VPS with a single command.

---

## Table of contents

1. [Goals and non-goals](#goals-and-non-goals)
2. [Features](#features)
3. [Tech stack](#tech-stack)
4. [Architecture](#architecture)
5. [Project structure](#project-structure)
6. [Configuration](#configuration)
7. [Behavior specification](#behavior-specification)
8. [Error handling](#error-handling)
9. [Security](#security)
10. [Run locally with Docker](#run-locally-with-docker)
11. [Deploy to a VPS](#deploy-to-a-vps)
12. [Maintenance](#maintenance)
13. [Roadmap](#roadmap)
14. [Instructions for the AI coding agent](#instructions-for-the-ai-coding-agent)
15. [Legal note](#legal-note)

---

## Goals and non-goals

### Goals

- Accept **any supported video link** and reply with the video file.
- Optimize for **short-form content** (Shorts, Reels, TikTok), typically 5 to 30 MB.
- Feel instant: cache results so a repeated link is answered without downloading again.
- Be stable under load: no crashes on bad links, no blocked event loop, no leaked temp files.
- Be trivially deployable: `docker compose up -d`.

### Non-goals

- Large files. Telegram's standard Bot API limit is **50 MB** and that is accepted for this project.
- Playlists, channels, live streams.
- A web UI. This is a Telegram-only product (for now).

---

## Features

| Feature | Description |
|---|---|
| 🔗 Link to video | Detects a URL in any message and downloads the video. |
| ▶️ Inline playback | Sends with correct `width`, `height`, `duration`, `supports_streaming` so it plays directly in chat. |
| ⚡ Smart cache | Stores Telegram `file_id` per normalized URL in SQLite. Repeat links are instant. |
| 🚦 Rate limiting | One active download per user and a global concurrency cap. |
| 🛡 Domain allowlist | Only configured platforms are accepted. |
| 🍪 Cookies support | Optional `cookies.txt` for Instagram and age-restricted content. |
| 📊 Admin stats | `/stats` for admins: users, downloads, cache hit rate, failures. |
| 🔄 Easy updates | yt-dlp is updated by rebuilding the image or via an admin command. |

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Language | Python 3.12 | Modern asyncio, typing. |
| Bot framework | aiogram 3.x | Fully async, clean routers and filters. |
| Downloader | yt-dlp | Supports hundreds of sites, actively maintained. |
| Media | ffmpeg | Merging streams, re-encoding when needed. |
| Storage | SQLite via `aiosqlite` | Zero-ops, enough for cache and stats. |
| Config | `pydantic-settings` | Typed settings from `.env`. |
| Logging | stdlib `logging`, structured format | Easy to read in `docker logs`. |
| Packaging | Docker, Docker Compose | Same environment on laptop and VPS. |

---

## Architecture

```
┌──────────┐   link    ┌────────────────────┐
│  Telegram │ ───────▶ │   aiogram handlers  │
│   user    │ ◀─────── │  (routers, filters) │
└──────────┘   video   └─────────┬──────────┘
                                 │
              ┌──────────────────┼───────────────────┐
              ▼                  ▼                   ▼
      ┌──────────────┐   ┌───────────────┐   ┌──────────────┐
      │ URL service   │   │ Cache service │   │ Rate limiter │
      │ validate +    │   │ SQLite        │   │ per-user lock│
      │ normalize     │   │ url → file_id │   │ + semaphore  │
      └──────┬───────┘   └───────────────┘   └──────────────┘
             ▼
      ┌──────────────────────────────┐
      │ Downloader service            │
      │ yt-dlp in a worker thread     │
      │ temp dir → ffmpeg → mp4   │
      └──────────────────────────────┘
```

**Request flow**

1. User sends a message containing a URL.
2. URL is extracted, validated against the allowlist and normalized (tracking params stripped).
3. Cache lookup. On hit, send by `file_id` and stop.
4. Acquire per-user lock and global semaphore.
5. Download in a worker thread (`asyncio.to_thread`) into a temp directory.
6. Send video with metadata, store the returned `file_id` in the cache.
7. Always clean up the temp directory and release locks (`finally`).

---

## Project structure

```
clipgrab-bot/
├── app/
│   ├── __init__.py
│   ├── main.py                # entrypoint: build bot, dispatcher, run polling
│   ├── config.py              # pydantic-settings Settings
│   ├── logging_setup.py
│   ├── db.py                  # aiosqlite connection, migrations, queries
│   ├── handlers/
│   │   ├── __init__.py
│   │   ├── start.py           # /start, /help
│   │   ├── link.py            # URL messages → video
│   │   └── admin.py           # /stats, /update_ytdlp
│   ├── services/
│   │   ├── __init__.py
│   │   ├── downloader.py      # yt-dlp wrapper (video, audio)
│   │   ├── cache.py           # url → file_id
│   │   ├── limiter.py         # per-user lock + global semaphore
│   │   └── urls.py            # extract, validate, normalize
│   └── texts.py               # all user-facing strings (Uzbek)
├── data/                      # SQLite DB (mounted volume)
├── cookies/                   # cookies.txt (mounted, optional, git-ignored)
├── tests/
│   ├── test_urls.py
│   └── test_cache.py
├── .env.example
├── .gitignore
├── .dockerignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

---

## Configuration

All settings come from environment variables (`.env`). Provide a complete `.env.example`.

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | required | Token from @BotFather. |
| `ADMIN_IDS` | empty | Comma-separated Telegram user IDs allowed to use admin commands. |
| `MAX_FILE_MB` | `50` | Max file size to download and send. |
| `MAX_DURATION_SEC` | `600` | Reject videos longer than this. |
| `MAX_CONCURRENT_DOWNLOADS` | `3` | Global concurrency cap. |
| `DOWNLOAD_TIMEOUT_SEC` | `120` | Hard timeout per download. |
| `ALLOWED_DOMAINS` | see below | Comma-separated domain allowlist. |
| `COOKIES_FILE` | empty | Path to `cookies.txt`, e.g. `/app/cookies/cookies.txt`. |
| `DB_PATH` | `/app/data/bot.db` | SQLite file path. |
| `LOG_LEVEL` | `INFO` | Logging level. |

Default `ALLOWED_DOMAINS`:
`youtube.com, youtu.be, tiktok.com, vm.tiktok.com, instagram.com, facebook.com, fb.watch, x.com, twitter.com, pinterest.com`

---

## Behavior specification

### Commands

| Command | Who | Behavior |
|---|---|---|
| `/start` | everyone | Short welcome in Uzbek and one example. Registers the user. |
| `/help` | everyone | Supported platforms, size limit, tips. |
| `/stats` | admins | Users, total downloads, cache hit rate, failures in the last 24h. |
| `/update_ytdlp` | admins | Runs `pip install -U yt-dlp`, reports the new version. |

### Link handling

- Any message containing an `http(s)` URL triggers processing. If several URLs exist, process the **first one** only.
- Show a status message: `⏳ Yuklanmoqda...` and edit it on completion or failure, or delete it on success.
- Send the chat action `upload_video` while working.

### Download rules

- Prefer **H.264 + AAC in an MP4 container** so Telegram plays it inline.
- Format selector (yt-dlp), in order of preference:
  1. `bv*[vcodec^=avc1][height<=1080]+ba[ext=m4a]`
  2. `b[ext=mp4]`
  3. `best`
- `noplaylist=True`, `max_filesize` from config, `socket_timeout` set, `quiet=True`.
- If the result is not H.264/AAC MP4, **re-encode with ffmpeg** (`libx264`, `aac`, `+faststart`) before sending.
- Reject if duration exceeds `MAX_DURATION_SEC` or size exceeds `MAX_FILE_MB`, with a clear message.

### Sending rules

- Use `answer_video` with `width`, `height`, `duration`, `supports_streaming=True`.
- Caption: short and clean, e.g. the platform name. No promotional text.
- Under the video, an inline button: `🎵 MP3`.
- After a successful send, store `normalized_url → file_id` in the cache.

### MP3 button

- Callback carries a short reference (cache row id), **not** the raw URL (Telegram callback data limit is 64 bytes).
- Extract audio with yt-dlp + ffmpeg (`mp3`, 192 kbps), send with `answer_audio`, cache its `file_id` separately.

### Concurrency

- One active download per user. A second request gets: `Avvalgi video yuklanyapti, biroz kuting 🙂`.
- A global `asyncio.Semaphore(MAX_CONCURRENT_DOWNLOADS)` protects the server.
- All blocking work runs in `asyncio.to_thread`. The event loop must never block.

### Database schema (SQLite)

```sql
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER PRIMARY KEY,
    username    TEXT,
    first_seen  TEXT NOT NULL DEFAULT (datetime('now')),
    last_seen   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channels (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    channel_id  TEXT NOT NULL UNIQUE,   -- @channel or -100xxx
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    url_key         TEXT NOT NULL UNIQUE,   -- normalized URL
    platform        TEXT,
    video_file_id   TEXT,
    audio_file_id   TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    url_key     TEXT NOT NULL,
    status      TEXT NOT NULL,              -- ok | cache_hit | failed
    error       TEXT,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### URL normalization

- Lowercase host, strip `www.` and `m.`.
- Remove tracking parameters (`utm_*`, `igshid`, `si`, `fbclid`, `feature`, etc.).
- Resolve short links (`vm.tiktok.com`, `youtu.be`) before building the cache key when possible.

---

## Error handling

Users must never see a stack trace. Map failures to friendly Uzbek messages (all strings live in `texts.py`):

| Situation | User message |
|---|---|
| URL not on allowlist | `Bu sayt qo'llab-quvvatlanmaydi.` |
| Private / login required | `Bu video yopiq yoki login talab qiladi.` |
| Too large | `Video 50 MB dan katta, yubora olmayman.` |
| Too long | `Video juda uzun.` |
| Timeout | `Yuklash juda uzoq davom etdi, keyinroq urinib ko'ring.` |
| Anything else | `Yuklab bo'lmadi. Link ochiq ekanini tekshiring.` |

Engineering rules:

- Catch `yt_dlp.utils.DownloadError` separately from unexpected exceptions.
- Log the full exception with `user_id` and URL at `ERROR`, but never log the bot token or cookies.
- Use `try/finally` for temp dirs, locks and the semaphore.
- Handle Telegram `TelegramRetryAfter` with a backoff retry.

---

## Security

- **Never** pass user input to a shell. Use the yt-dlp Python API and `subprocess` with argument lists only.
- Accept only `http` and `https` schemes. Reject IPs, `localhost`, and private ranges (SSRF protection) in addition to the domain allowlist.
- Keep secrets in `.env` and `cookies/`. Both are git-ignored and docker-ignored.
- Run the container as a **non-root user**.
- Admin commands are protected by `ADMIN_IDS`.
- Temp files are deleted immediately after sending.

---

## Run locally with Docker

```bash
git clone <your-repo-url> clipgrab-bot
cd clipgrab-bot
cp .env.example .env        # set BOT_TOKEN
docker compose up --build
```

Then open your bot in Telegram, send `/start`, and paste a Shorts or TikTok link.

### Dockerfile (reference)

```dockerfile
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 bot
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -U -r requirements.txt

COPY app ./app
RUN mkdir -p /app/data /app/cookies && chown -R bot:bot /app
USER bot

CMD ["python", "-m", "app.main"]
```

### docker-compose.yml (reference)

```yaml
services:
  bot:
    build: .
    container_name: clipgrab-bot
    env_file: .env
    restart: unless-stopped
    volumes:
      - ./data:/app/data
      - ./cookies:/app/cookies:ro
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
```

### requirements.txt

```
aiogram>=3.13
yt-dlp
aiosqlite
pydantic-settings
```

---

## Deploy to a VPS

Tested flow for a fresh Ubuntu 22.04 / 24.04 server:

```bash
# 1. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 2. Get the code
git clone <your-repo-url> clipgrab-bot && cd clipgrab-bot

# 3. Configure
cp .env.example .env && nano .env

# 4. Launch
docker compose up -d --build

# 5. Watch logs
docker compose logs -f
```

Update later:

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

The bot uses **long polling**, so no domain, SSL or open ports are required.

---

## Maintenance

- **yt-dlp goes stale quickly.** Sites change often. Rebuild the image with `--no-cache` weekly, or use `/update_ytdlp`.
- Back up `data/bot.db` if you care about the cache and stats.
- Monitor with `docker compose logs -f` and `/stats`.
- If Instagram or YouTube starts failing from the VPS IP, add fresh `cookies.txt` exported from a logged-in browser.

---

## Roadmap

- [ ] Quality picker (360p / 720p / 1080p)
- [ ] Inline mode
- [ ] Multi-language UI (uz, ru, en)
- [ ] Optional Local Bot API server for files up to 2 GB
- [ ] Prometheus metrics endpoint
- [ ] Webhook mode behind a reverse proxy

---

## Instructions for the AI coding agent

You are implementing this project end to end. Follow these rules:

1. **Build exactly the structure above.** Do not collapse modules into one file.
2. **Async everywhere.** Any blocking call (yt-dlp, ffmpeg, file IO) goes through `asyncio.to_thread` or an async library.
3. **Type hints and docstrings** on all public functions. Keep functions small and single-purpose.
4. **All user-facing text** lives in `app/texts.py`, in Uzbek.
5. **No hard-coded secrets or paths.** Everything via `Settings`.
6. **Write tests** for URL extraction, validation, normalization and the cache layer (`pytest`, `pytest-asyncio`).
7. **Deliver working infrastructure:** `Dockerfile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `.dockerignore`.
8. Implement in this order and verify each step before moving on:
   1. config, logging, DB init
   2. URL service and tests
   3. downloader service
   4. link handler (video send)
   5. cache
   6. limiter
   8. admin commands
   9. Docker run end to end

### Acceptance criteria

- [ ] `docker compose up --build` starts the bot with no errors.
- [ ] A public YouTube Short, TikTok and Instagram Reel link each return a playable video.
- [ ] Sending the same link twice returns instantly the second time (cache hit logged).
- [ ] Two rapid requests from one user: the second is politely rejected.
- [ ] An invalid or unsupported link returns a friendly message, no crash.
- [ ] Temp directories are empty after each request.
- [ ] `/stats` works for admins and is denied for others.
- [ ] `pytest` passes.

---

## Legal note

This tool is intended for personal use. Downloading content may violate a platform's terms of service or the copyright of its creators. Only download content you own or have permission to save, and respect the rights of creators.

---

## License

MIT
