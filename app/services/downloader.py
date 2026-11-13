"""Media download service using yt-dlp and ffmpeg."""

import asyncio
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
import yt_dlp

logger = logging.getLogger(__name__)


def _find_binary(name: str) -> str:
    """Find binary in PATH or common fallback locations."""
    path = shutil.which(name)
    if path:
        return path
    for cand in (
        os.path.expanduser(f"~/bin/{name}"),
        os.path.expanduser(f"~/.local/bin/{name}"),
        f"/usr/local/bin/{name}",
        f"/usr/bin/{name}",
    ):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return name


class DownloaderError(Exception):
    """Base exception for downloader errors."""

    pass


class VideoTooLargeError(DownloaderError):
    """Raised when the video exceeds the maximum file size."""

    pass


class VideoTooLongError(DownloaderError):
    """Raised when the video exceeds the maximum duration."""

    pass


class PrivateOrLoginRequiredError(DownloaderError):
    """Raised when content is private, deleted, or requires login."""

    pass


class ContentBlockedError(DownloaderError):
    """Raised when the content policy rejects the video before it is downloaded."""

    def __init__(self, category: Optional[str] = None, term: Optional[str] = None, source: Optional[str] = None):
        self.category, self.term, self.source = category, term, source
        super().__init__(f"content blocked: {category} ({source}: {term})")


class DownloadTimeoutError(DownloaderError):
    """Raised when the download times out."""

    pass


class DownloadFailedError(DownloaderError):
    """Raised when the download fails unexpectedly."""

    pass


@dataclass
class VideoResult:
    """Result of a video download."""

    file_path: str
    width: Optional[int]
    height: Optional[int]
    duration: Optional[int]
    platform: Optional[str]
    title: Optional[str]


def _is_h264_aac_mp4(file_path: str) -> bool:
    """Check if file is already a fast MP4."""
    return file_path.lower().endswith(".mp4")


def _reencode_video(input_path: str, output_path: str) -> str:
    """Fast remux with +faststart for instant inline Telegram playback without heavy CPU re-encoding."""
    ffmpeg_bin = _find_binary("ffmpeg")
    cmd_copy = [
        ffmpeg_bin,
        "-y",
        "-i",
        input_path,
        "-c",
        "copy",
        "-movflags",
        "+faststart",
        output_path,
    ]
    try:
        res = subprocess.run(cmd_copy, capture_output=True)
        if res.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        logger.debug("Fast stream copy failed: %s", e)

    cmd_encode = [
        ffmpeg_bin,
        "-y",
        "-i",
        input_path,
        "-c:v",
        "libx264",
        "-preset",
        "ultrafast",
        "-crf",
        "25",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        output_path,
    ]
    try:
        res = subprocess.run(cmd_encode, capture_output=True)
        if res.returncode == 0 and os.path.isfile(output_path) and os.path.getsize(output_path) > 0:
            return output_path
    except Exception as e:
        logger.warning("Ultrafast encode failed: %s", e)

    return input_path


def _classify_yt_dlp_error(err_str: str) -> DownloaderError:
    """Map yt-dlp error string to appropriate exception."""
    lowered = err_str.lower()
    if any(
        kw in lowered
        for kw in (
            "this video is private",
            "account is private",
            "members-only",
            "video unavailable",
            "private video",
        )
    ):
        return PrivateOrLoginRequiredError(err_str)
    if "maximum file size exceeded" in lowered or "file is larger than" in lowered:
        return VideoTooLargeError(err_str)
    return DownloadFailedError(err_str)


def _sync_download_video(
    url: str,
    output_dir: str,
    max_file_mb: int,
    max_duration_sec: int,
    timeout_sec: int,
    cookies_file: Optional[str] = None,
    content_check: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> VideoResult:
    """Synchronous video download worker intended to run in a thread.

    content_check(info) -> Verdict-like object (with .blocked/.category/.term/.source).
    It runs on yt-dlp's metadata through match_filter, i.e. BEFORE any media bytes are
    downloaded; a blocked video raises ContentBlockedError."""
    max_file_bytes = max_file_mb * 1024 * 1024
    outtmpl = os.path.join(output_dir, "%(id)s.%(ext)s")

    format_spec = (
        f"bv*[ext=mp4][height<=1080][filesize<{max_file_mb}M]+ba[ext=m4a]"
        f"/b[ext=mp4][height<=1080][filesize<{max_file_mb}M]"
        f"/bv*[height<=720][filesize<{max_file_mb}M]+ba"
        f"/b[height<=720][filesize<{max_file_mb}M]"
        f"/bv*[height<=720]+ba/b[height<=720]/bv*+ba/b/best"
    )

    ydl_opts: Dict[str, Any] = {
        "format": format_spec,
        "outtmpl": outtmpl,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": min(timeout_sec, 20),
        "retries": 3,
        "fragment_retries": 3,
        "concurrent_fragment_downloads": 5,
        "buffersize": 1024 * 1024,
        "js_runtimes": {"node": {}, "deno": {}},
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        },
    }

    blocked_box: list = []
    if content_check is not None:

        def _match_filter(info_dict: Dict[str, Any], *, incomplete: bool = False) -> Optional[str]:
            verdict = content_check(info_dict)
            if verdict.blocked:
                blocked_box.append(verdict)
                return "Blocked by content policy"  # non-None: yt-dlp skips the download
            return None

        ydl_opts["match_filter"] = _match_filter

    ffmpeg_bin = _find_binary("ffmpeg")
    if os.path.dirname(ffmpeg_bin):
        ydl_opts["ffmpeg_location"] = os.path.dirname(ffmpeg_bin)

    if not cookies_file or not os.path.isfile(cookies_file):
        for cand in (
            "cookies/cookies.txt",
            os.path.join(os.getcwd(), "cookies", "cookies.txt"),
            os.path.expanduser("~/savebot/cookies/cookies.txt"),
        ):
            if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                cookies_file = cand
                break

    if cookies_file and os.path.isfile(cookies_file) and os.path.getsize(cookies_file) > 0:
        ydl_opts["cookiefile"] = cookies_file
        ydl_opts["remote_components"] = ["ejs:github"]
        ydl_opts["js_runtimes"] = {"node": {}, "deno": {}}
    else:
        ydl_opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android"]
            }
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Single-pass download for maximum speed
            download_info = ydl.extract_info(url, download=True)
            if blocked_box:
                v = blocked_box[0]
                raise ContentBlockedError(v.category, v.term, v.source)
            if not download_info:
                raise DownloadFailedError("Download failed")

            if "entries" in download_info:
                entries = [e for e in download_info["entries"] if e]
                if entries:
                    download_info = entries[0]

            duration = download_info.get("duration")
            if duration and duration > max_duration_sec:
                raise VideoTooLongError(f"Video duration ({duration}s) exceeds {max_duration_sec}s")

            downloaded_file = ydl.prepare_filename(download_info)

            # Check if merged mp4 exists
            base, _ = os.path.splitext(downloaded_file)
            mp4_file = base + ".mp4"
            if os.path.isfile(mp4_file):
                downloaded_file = mp4_file

            if not os.path.isfile(downloaded_file):
                # Search directory for whatever was saved
                candidates = []
                for root, _, files in os.walk(output_dir):
                    for f in files:
                        p = os.path.join(root, f)
                        if os.path.isfile(p) and not f.endswith((".part", ".ytdl")):
                            candidates.append(p)
                if candidates:
                    candidates.sort(key=lambda x: os.path.getsize(x), reverse=True)
                    downloaded_file = candidates[0]
                else:
                    raise DownloadFailedError("Downloaded file could not be located on disk")

            # Check file size
            file_size = os.path.getsize(downloaded_file)
            if file_size > max_file_bytes:
                raise VideoTooLargeError(f"File size ({file_size} bytes) exceeds limit")

            # Fast remux / stream copy for inline Telegram playback if needed
            final_file = downloaded_file
            if not _is_h264_aac_mp4(downloaded_file):
                reencoded_path = os.path.join(output_dir, "reencoded.mp4")
                final_file = _reencode_video(downloaded_file, reencoded_path)

            if not os.path.isfile(final_file):
                raise DownloadFailedError("Final video file could not be located on disk")

            # Re-check size of final file
            if os.path.getsize(final_file) > max_file_bytes:
                raise VideoTooLargeError("Re-encoded video exceeds size limit")

            w = download_info.get("width")
            h = download_info.get("height")
            d = download_info.get("duration")

            return VideoResult(
                file_path=final_file,
                width=int(w) if w is not None else None,
                height=int(h) if h is not None else None,
                duration=int(round(float(d))) if d is not None else None,
                platform=download_info.get("extractor_key"),
                title=download_info.get("title"),
            )

    except yt_dlp.utils.DownloadError as e:
        raise _classify_yt_dlp_error(str(e)) from e
    except DownloaderError:
        raise
    except Exception as e:
        logger.exception("Unexpected download error: %s", e)
        raise DownloadFailedError(str(e)) from e


async def download_video(
    url: str,
    output_dir: str,
    max_file_mb: int = 50,
    max_duration_sec: int = 600,
    timeout_sec: int = 120,
    cookies_file: Optional[str] = None,
    content_check: Optional[Callable[[Dict[str, Any]], Any]] = None,
) -> VideoResult:
    """Asynchronously download video with a timeout."""
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(
                _sync_download_video,
                url=url,
                output_dir=output_dir,
                max_file_mb=max_file_mb,
                max_duration_sec=max_duration_sec,
                timeout_sec=timeout_sec,
                cookies_file=cookies_file,
                content_check=content_check,
            ),
            timeout=float(timeout_sec),
        )
    except asyncio.TimeoutError:
        raise DownloadTimeoutError("Download timed out")
