"""URL extraction, validation, and normalization service."""

import ipaddress
import logging
import re
from typing import List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import aiohttp

logger = logging.getLogger(__name__)

URL_REGEX = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)

TRACKING_PARAM_PREFIXES = ("utm_",)
TRACKING_PARAMS = {
    "igshid",
    "si",
    "fbclid",
    "feature",
    "ref",
    "ref_src",
    "share_id",
    "share_app_id",
    "is_copy_url",
    "is_from_webapp",
    "sender_device",
    "context",
    "m",
    "mibextid",
    "rdid",
    "share_url",
}


def extract_first_url(text: str) -> Optional[str]:
    """Find and return the first HTTP/HTTPS URL from text."""
    if not text:
        return None
    match = URL_REGEX.search(text)
    if not match:
        return None
    url = match.group(0).rstrip(".,;:!?)")
    return url


def is_ip_or_private_host(hostname: str) -> bool:
    """Check if host is an IP address or private/localhost (SSRF protection)."""
    if not hostname:
        return True
    clean_host = hostname.strip().lower()

    if clean_host in {"localhost", "loopback"} or clean_host.endswith(
        (".local", ".internal", ".lan")
    ):
        return True

    # Check if host is an IP address (IPv4 or IPv6)
    # README: "Reject IPs, localhost, and private ranges"
    try:
        ip = ipaddress.ip_address(clean_host)
        # Any direct IP or private IP is rejected
        return True
    except ValueError:
        pass

    return False


def clean_hostname(hostname: str) -> str:
    """Lowercase and strip leading www. or m. from hostname."""
    host = hostname.strip().lower()
    if host.startswith("www."):
        host = host[4:]
    elif host.startswith("m."):
        host = host[2:]
    return host


def is_domain_allowed(hostname: str, allowed_domains: List[str]) -> bool:
    """Verify if domain is in the allowed platforms list."""
    host = clean_hostname(hostname)
    for domain in allowed_domains:
        d = domain.strip().lower()
        if host == d or host.endswith("." + d):
            return True
    return False


def validate_url(url: str, allowed_domains: List[str]) -> Tuple[bool, Optional[str]]:
    """Validate URL scheme, safety (SSRF/IP), and domain allowlist."""
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "Invalid URL structure"

    if parsed.scheme.lower() not in ("http", "https"):
        return False, "Only HTTP and HTTPS schemes are supported"

    hostname = parsed.hostname
    if not hostname:
        return False, "Missing hostname"

    if is_ip_or_private_host(hostname):
        return False, "Direct IP addresses and local networks are not allowed"

    if not is_domain_allowed(hostname, allowed_domains):
        return False, "Domain not in allowed platforms"

    return True, None


def normalize_url(url: str) -> str:
    """
    Normalize URL for consistent caching:
    - Lowercase scheme and netloc.
    - Strip 'www.' and 'm.'.
    - Transform shorthand domains (youtu.be -> youtube.com/watch?v=...).
    - Remove tracking query parameters (utm_*, igshid, si, fbclid, etc.).
    - Remove fragments and trailing slashes.
    """
    parsed = urlparse(url)
    scheme = "https"
    netloc = clean_hostname(parsed.hostname or "")
    path = parsed.path.rstrip("/")
    if not path:
        path = "/"

    # Normalize YouTube shortlinks
    if netloc == "youtu.be":
        netloc = "youtube.com"
        video_id = path.lstrip("/")
        path = "/watch"
        query_items = [("v", video_id)]
    else:
        query_items = []
        for k, v in parse_qsl(parsed.query, keep_blank_values=False):
            k_lower = k.lower()
            if any(k_lower.startswith(p) for p in TRACKING_PARAM_PREFIXES):
                continue
            if k_lower in TRACKING_PARAMS:
                continue
            query_items.append((k, v))

    # Sort remaining query items for deterministic cache key
    query_items.sort(key=lambda x: x[0])
    query_str = urlencode(query_items)

    return urlunparse((scheme, netloc, path, "", query_str, ""))


async def resolve_redirects(url: str, timeout_sec: int = 8) -> str:
    """Follow HTTP redirects for shortlinks and mobile share links (e.g. facebook.com/share)."""
    # Only resolve if URL looks like a redirect / share pattern
    url_lower = url.lower()
    needs_resolve = any(
        kw in url_lower
        for kw in (
            "/share/",
            "fb.watch",
            "vm.tiktok.com",
            "vt.tiktok.com",
            "youtu.be",
            "pin.it",
        )
    )
    if not needs_resolve:
        return url

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/128.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    try:
        timeout = aiohttp.ClientTimeout(total=float(timeout_sec))
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            try:
                async with session.head(url, allow_redirects=True) as resp:
                    if resp.status < 400 and str(resp.url) != url:
                        return str(resp.url)
            except Exception:
                pass
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status < 400:
                    return str(resp.url)
    except Exception as e:
        logger.debug("Failed to resolve redirect for %s: %s", url, e)
    return url
