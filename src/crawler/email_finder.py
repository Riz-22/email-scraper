thonimport asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Set, Tuple

import aiohttp

from crawler import utils
from crawler.validator import validate_email_domain

@dataclass(frozen=True)
class EmailResult:
    email: str
    dnsLookup: bool

async def _worker(
    name: str,
    session: aiohttp.ClientSession,
    queue: "asyncio.Queue[Tuple[str, int]]",
    visited: Set[str],
    max_depth: int,
    dns_validate: bool,
    found_emails: Dict[str, bool],
    proxy: Optional[str],
    request_timeout: float,
    allowed_domains: Optional[Set[str]],
) -> None:
    logger = logging.getLogger(f"worker-{name}")
    while True:
        try:
            url, depth = await queue.get()
        except asyncio.CancelledError:
            break

        try:
            if url in visited:
                queue.task_done()
                continue
            visited.add(url)

            if allowed_domains:
                domain = utils.get_domain(url)
                if domain and domain not in allowed_domains:
                    logger.debug("Skipping %s (domain not allowed)", url)
                    queue.task_done()
                    continue

            logger.debug("Fetching %s at depth %d", url, depth)
            try:
                html = await utils.fetch_html(
                    session=session,
                    url=url,
                    proxy=proxy,
                    timeout=request_timeout,
                )
            except Exception as exc:
                logger.warning("Failed to fetch %s: %s", url, exc)
                queue.task_done()
                continue

            # Extract and validate emails from this page
            for email in utils.extract_emails(html):
                if email not in found_emails:
                    if dns_validate:
                        try:
                            is_valid = await validate_email_domain(email)
                        except Exception as exc:
                            logger.debug("DNS validation failed for %s: %s", email, exc)
                            is_valid = False
                    else:
                        is_valid = True
                    found_emails[email] = is_valid
                    logger.debug("Discovered email %s (dnsLookup=%s)", email, is_valid)

            # Enqueue next-level links
            if depth < max_depth:
                for link in utils.extract_links(url, html):
                    if link not in visited:
                        await queue.put((link, depth + 1))
        finally:
            queue.task_done()

async def crawl_and_collect_emails(
    start_urls: Iterable[str],
    max_depth: int,
    concurrency: int,
    request_timeout: float,
    dns_validate: bool = True,
    proxy: Optional[str] = None,
    allowed_domains: Optional[Set[str]] = None,
) -> List[EmailResult]:
    """
    Crawl starting from the given URLs and collect unique email addresses.

    :param start_urls: Iterable of starting URLs.
    :param max_depth: Maximum depth of recursion (0 = only the given URLs).
    :param concurrency: Maximum number of concurrent HTTP requests.
    :param request_timeout: HTTP request timeout in seconds.
    :param dns_validate: If True, validate email domains using DNS.
    :param proxy: Optional HTTP proxy URL.
    :param allowed_domains: Optional set of allowed domains to restrict crawling.
    :return: List of EmailResult with unique emails and DNS validation flag.
    """
    logger = logging.getLogger("email_finder")
    start_urls = [utils.normalize_url(u) for u in start_urls if u]

    if not start_urls:
        logger.warning("No valid start URLs provided.")
        return []

    visited: Set[str] = set()
    found_emails: Dict[str, bool] = {}

    queue: "asyncio.Queue[Tuple[str, int]]" = asyncio.Queue()
    for url in start_urls:
        await queue.put((url, 0))

    timeout = aiohttp.ClientTimeout(total=request_timeout)
    headers = {
        "User-Agent": utils.DEFAULT_USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        workers = [
            asyncio.create_task(
                _worker(
                    name=str(i),
                    session=session,
                    queue=queue,
                    visited=visited,
                    max_depth=max_depth,
                    dns_validate=dns_validate,
                    found_emails=found_emails,
                    proxy=proxy,
                    request_timeout=request_timeout,
                    allowed_domains=allowed_domains,
                )
            )
            for i in range(concurrency)
        ]

        logger.info(
            "Starting crawl with %d workers, depth=%d, dns_validate=%s",
            concurrency,
            max_depth,
            dns_validate,
        )

        try:
            await queue.join()
        finally:
            for w in workers:
                w.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    results = [EmailResult(email=e, dnsLookup=valid) for e, valid in sorted(found_emails.items())]
    logger.info("Crawl finished. Found %d unique email(s).", len(results))
    return results