"""Unit tests for URL extraction, validation, and normalization."""

import pytest
from app.services.urls import (
    extract_first_url,
    validate_url,
    normalize_url,
)

ALLOWED = [
    "youtube.com",
    "youtu.be",
    "tiktok.com",
    "vm.tiktok.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "x.com",
    "twitter.com",
    "pinterest.com",
]


def test_extract_first_url() -> None:
    # No url
    assert extract_first_url("Salom, qandaysiz?") is None
    assert extract_first_url("") is None

    # Single url with trailing punctuation
    text1 = "Mana bu videoni ko'ring: https://www.tiktok.com/@user/video/123456789!"
    assert extract_first_url(text1) == "https://www.tiktok.com/@user/video/123456789"

    # Multiple urls, extract first only
    text2 = "1. https://youtu.be/dQw4w9WgXcQ va 2. https://instagram.com/reel/abc123"
    assert extract_first_url(text2) == "https://youtu.be/dQw4w9WgXcQ"


def test_validate_url_allowed_domains() -> None:
    valid_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://m.tiktok.com/v/123.html",
        "https://vm.tiktok.com/ZM8abc/",
        "https://www.instagram.com/reel/C123456/",
        "https://x.com/user/status/123456789",
    ]
    for url in valid_urls:
        is_valid, err = validate_url(url, ALLOWED)
        assert is_valid is True, f"Expected {url} to be valid, got: {err}"


def test_validate_url_rejected_domains_and_schemes() -> None:
    invalid_urls = [
        "https://malicious-site.com/video.mp4",
        "ftp://youtube.com/watch?v=123",
        "javascript:alert(1)",
        "http://example.org",
    ]
    for url in invalid_urls:
        is_valid, _ = validate_url(url, ALLOWED)
        assert is_valid is False, f"Expected {url} to be rejected"


def test_validate_url_ssrf_protection() -> None:
    ssrf_targets = [
        "http://127.0.0.1/admin",
        "http://localhost:8080/info",
        "http://192.168.1.1/router",
        "http://10.0.0.1/secret",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/status",
    ]
    for url in ssrf_targets:
        is_valid, _ = validate_url(url, ALLOWED)
        assert is_valid is False, f"Expected {url} to be blocked by SSRF check"


def test_normalize_url_strips_tracking() -> None:
    dirty_url = (
        "https://www.instagram.com/reel/C123456/"
        "?utm_source=ig_web_copy_link&igshid=MzRlODBiNWFlZA==&si=abcdef"
    )
    normalized = normalize_url(dirty_url)
    assert "utm_source" not in normalized
    assert "igshid" not in normalized
    assert "si" not in normalized
    assert normalized == "https://instagram.com/reel/C123456"


def test_normalize_url_youtube_shortlink() -> None:
    short_url = "https://youtu.be/dQw4w9WgXcQ?si=tracking123"
    normalized = normalize_url(short_url)
    assert normalized == "https://youtube.com/watch?v=dQw4w9WgXcQ"


def test_normalize_url_removes_www_and_m() -> None:
    url_www = "https://www.tiktok.com/@user/video/789?is_from_webapp=1"
    assert normalize_url(url_www) == "https://tiktok.com/@user/video/789"

    url_m = "https://m.facebook.com/watch/?v=12345&fbclid=abc"
    assert normalize_url(url_m) == "https://facebook.com/watch?v=12345"
