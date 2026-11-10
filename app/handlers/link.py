"""Link handler for URL messages, processing video downloads and caching."""

import asyncio
import logging
import tempfile
from typing import Any
from aiogram import F, Router
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import FSInputFile, Message

from app import texts
from app.config import settings
from app.db import record_download, upsert_user
from app.services.cache import get_cache_by_url, save_video_cache
from app.services.downloader import (
    DownloadFailedError,
    DownloadTimeoutError,
    PrivateOrLoginRequiredError,
    VideoTooLargeError,
    VideoTooLongError,
    download_video,
)
from app.services.limiter import UserBusyError, limiter
from app.services.subscription import check_user_subscriptions, get_subscription_keyboard
from app.services.urls import extract_first_url, normalize_url, resolve_redirects, validate_url

logger = logging.getLogger(__name__)
router = Router(name="link")


async def _send_video_with_retry(message: Message, **kwargs: Any) -> Message:
    """Send video with retry backoff on Telegram flood limits."""
    for k in ("duration", "width", "height"):
        val = kwargs.get(k)
        if val is not None:
            try:
                kwargs[k] = int(round(float(val)))
            except (ValueError, TypeError):
                kwargs[k] = None

    for attempt in range(3):
        try:
            return await message.answer_video(**kwargs)
        except TelegramRetryAfter as e:
            logger.warning("Telegram flood control, sleeping for %s seconds", e.retry_after)
            if attempt < 2:
                await asyncio.sleep(e.retry_after + 1)
            else:
                raise


@router.message(F.text)
async def handle_link_message(message: Message) -> None:
    """Detect URLs in message text, download video, and reply inline."""
    if not message.text or not message.from_user:
        return

    # Extract first URL
    raw_url = extract_first_url(message.text)
    if not raw_url:
        return

    user_id = message.from_user.id
    username = message.from_user.username

    # Register/update user activity
    await upsert_user(settings.db_path, user_id=user_id, username=username)

    # Check sponsor channel subscription
    is_sub, unsub = await check_user_subscriptions(
        bot=message.bot,
        user_id=user_id,
        db_path=settings.db_path,
    )
    if not is_sub:
        keyboard = get_subscription_keyboard(unsub)
        await message.reply(texts.SUB_REQUIRED, reply_markup=keyboard, parse_mode="HTML")
        return

    # Validate URL against allowlist and SSRF checks
    is_valid, reason = validate_url(raw_url, settings.allowed_domains)
    if not is_valid:
        logger.info("URL validation rejected for user %s: %s (reason: %s)", user_id, raw_url, reason)
        await message.reply(texts.ERR_NOT_ALLOWED)
        await record_download(settings.db_path, user_id, raw_url, "failed", reason)
        return

    # Follow mobile redirects if needed (e.g. facebook.com/share/v/..., fb.watch/...)
    resolved_url = await resolve_redirects(raw_url)
    if resolved_url != raw_url:
        is_valid_res, _ = validate_url(resolved_url, settings.allowed_domains)
        if is_valid_res:
            raw_url = resolved_url

    # Normalize URL to canonical form
    url_key = normalize_url(raw_url)

    # Cache lookup
    cached = await get_cache_by_url(settings.db_path, url_key)
    if cached and cached.video_file_id:
        logger.info("Cache hit for user %s: %s", user_id, url_key)
        try:
            await message.bot.send_chat_action(chat_id=message.chat.id, action="upload_video")
            await _send_video_with_retry(
                message=message,
                video=cached.video_file_id,
                caption=cached.platform or "Video",
                supports_streaming=True,
            )
            await record_download(settings.db_path, user_id, url_key, "cache_hit")
            return
        except Exception as e:
            logger.warning("Failed to send cached file_id, will re-download: %s", e)

    # Acquire rate limiter
    try:
        async with limiter.throttle(user_id):
            status_msg = await message.reply(texts.STATUS_DOWNLOADING)

            # Inform user of chat action
            await message.bot.send_chat_action(chat_id=message.chat.id, action="upload_video")

            # Temporary directory for video download and optional re-encoding
            with tempfile.TemporaryDirectory() as temp_dir:
                try:
                    video_res = await download_video(
                        url=url_key,
                        output_dir=temp_dir,
                        max_file_mb=settings.max_file_mb,
                        max_duration_sec=settings.max_duration_sec,
                        timeout_sec=settings.download_timeout_sec,
                        cookies_file=settings.cookies_file,
                    )

                    # Send video to user
                    sent_msg = await _send_video_with_retry(
                        message=message,
                        video=FSInputFile(video_res.file_path),
                        width=video_res.width,
                        height=video_res.height,
                        duration=video_res.duration,
                        caption=video_res.platform or "Video",
                        supports_streaming=True,
                    )

                    # Store Telegram file_id in cache
                    if sent_msg.video:
                        await save_video_cache(
                            db_path=settings.db_path,
                            url_key=url_key,
                            platform=video_res.platform,
                            video_file_id=sent_msg.video.file_id,
                        )

                    # Delete progress message on success
                    try:
                        await status_msg.delete()
                    except Exception:
                        pass

                    await record_download(settings.db_path, user_id, url_key, "ok")
                    logger.info("Successfully downloaded and sent video for user %s", user_id)

                except VideoTooLargeError:
                    await status_msg.edit_text(texts.ERR_TOO_LARGE)
                    await record_download(settings.db_path, user_id, url_key, "failed", "too_large")
                except VideoTooLongError:
                    await status_msg.edit_text(texts.ERR_TOO_LONG)
                    await record_download(settings.db_path, user_id, url_key, "failed", "too_long")
                except PrivateOrLoginRequiredError:
                    await status_msg.edit_text(texts.ERR_PRIVATE_OR_LOGIN)
                    await record_download(settings.db_path, user_id, url_key, "failed", "private")
                except DownloadTimeoutError:
                    await status_msg.edit_text(texts.ERR_TIMEOUT)
                    await record_download(settings.db_path, user_id, url_key, "failed", "timeout")
                except Exception as e:
                    logger.error("Download error for user %s (%s): %s", user_id, url_key, e)
                    await status_msg.edit_text(texts.ERR_GENERAL)
                    await record_download(settings.db_path, user_id, url_key, "failed", str(e))

    except UserBusyError:
        await message.reply(texts.ERR_ALREADY_DOWNLOADING)
