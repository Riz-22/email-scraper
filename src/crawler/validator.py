thonimport asyncio
import logging
import socket
from typing import Optional

logger = logging.getLogger("validator")

def _extract_domain(email: str) -> Optional[str]:
    if "@" not in email:
        return None
    local, domain = email.rsplit("@", 1)
    local = local.strip()
    domain = domain.strip().strip("[]")
    if not local or not domain:
        return None
    # very small sanity check
    if "." not in domain:
        return None
    return domain.lower()

def _resolve_domain(domain: str) -> bool:
    """
    Blocking DNS lookup using socket.gethostbyname.
    Returns True if resolution succeeds, False otherwise.
    """
    try:
        socket.gethostbyname(domain)
        return True
    except OSError as exc:
        logger.debug("DNS resolution failed for %s: %s", domain, exc)
        return False

async def validate_email_domain(email: str) -> bool:
    """
    Validate the domain part of an email address using a DNS lookup.

    The function is implemented asynchronously by delegating the blocking DNS
    call to a thread pool executor, so it won't block the event loop.

    :param email: Email address to validate.
    :return: True if the domain resolves, False otherwise.
    """
    domain = _extract_domain(email)
    if not domain:
        logger.debug("Skipping DNS validation for malformed email: %s", email)
        return False

    loop = asyncio.get_running_loop()
    valid = await loop.run_in_executor(None, _resolve_domain, domain)
    logger.debug("DNS validation for %s (%s): %s", email, domain, valid)
    return valid