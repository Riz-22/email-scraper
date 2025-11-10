thonimport logging
import re
from typing import Iterable, List, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger("utils")

EMAIL_REGEX = re.compile(
    r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9.-]+",
    re.IGNORECASE,
)

DEFAULT_USER_AGENT = (
    "EmailScraperBot/1.0 (+https://example.com; contact: email-scraper@example.com)"
)

async def fetch_html(
    session: aiohttp.ClientSession,
    url: str,
    proxy: Optional[str],
    timeout: float,
) -> str:
    """
    Fetch HTML from a URL using aiohttp.

    :param session: Shared aiohttp.ClientSession.
    :param url: Target URL.
    :param proxy: Optional proxy URL.
    :param timeout: Request timeout (not strictly needed here, kept for compatibility).
    :return: HTML text.
    :raises: Exception if the request fails.
    """
    try:
        async with session.get(url, proxy=proxy) as response:
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                logger.debug("Skipping non-HTML content at %s (%s)", url, content_type)
                return ""
            text = await response.text(errors="ignore")
            return text
    except asyncio.CancelledError:  # type: ignore[name-defined]
        raise
    except Exception as exc:
        logger.warning("HTTP error while fetching %s: %s", url, exc)
        raise

def normalize_url(url: str) -> str:
    """
    Normalize a URL by stripping fragments, default ports, and whitespace.
    """
    url = url.strip()
    if not url:
        return url

    parsed = urlparse(url)
    if not parsed.scheme:
        # Assume HTTP if scheme is missing
        parsed = parsed._replace(scheme="http")

    netloc = parsed.netloc
    if netloc.endswith(":80") and parsed.scheme == "http":
        netloc = netloc[:-3]
    elif netloc.endswith(":443") and parsed.scheme == "https":
        netloc = netloc[:-4]

    parsed = parsed._replace(fragment="", netloc=netloc)
    normalized = urlunparse(parsed)
    return normalized

def get_domain(url: str) -> Optional[str]:
    parsed = urlparse(url)
    return parsed.hostname.lower() if parsed.hostname else None

def extract_emails(html: str) -> List[str]:
    """
    Extract potential email addresses from HTML text using a regex.
    """
    if not html:
        return []
    emails = set(match.group(0) for match in EMAIL_REGEX.finditer(html))
    # Very basic cleanup: lowercase and strip trailing punctuation
    cleaned = {
        e.strip().strip(".,;:()[]<>").lower()
        for e in emails
        if "@" in e
    }
    return sorted(cleaned)

def extract_links(base_url: str, html: str) -> List[str]:
    """
    Extract all HTTP/HTTPS links from an HTML document, normalized and deduplicated.
    """
    if not html:
        return []

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:
        logger.debug("Failed to parse HTML from %s: %s", base_url, exc)
        return []

    links = set()
    for tag in soup.find_all("a", href=True):
        href = tag.get("href") or ""
        href = href.strip()
        if not href or href.startswith("mailto:") or href.startswith("javascript:"):
            continue
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        cleaned = urlunparse(parsed._replace(fragment=""))
        links.add(cleaned)

    return sorted(links)