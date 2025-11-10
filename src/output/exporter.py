thonimport json
import logging
from pathlib import Path
from typing import Iterable, Mapping, Any, Optional

logger = logging.getLogger("exporter")

def _serialize_item(item: Any) -> Optional[dict]:
    """
    Convert a result item into a JSON-serializable dict with keys
    `email` and `dnsLookup`.
    """
    if isinstance(item, Mapping):
        email = item.get("email")
        dns = bool(item.get("dnsLookup", False))
    else:
        email = getattr(item, "email", None)
        dns = bool(getattr(item, "dnsLookup", False))

    if not email:
        return None

    return {
        "email": str(email),
        "dnsLookup": bool(dns),
    }

def export_results(results: Iterable[Any], output_path: Path) -> None:
    """
    Export scraping results to a JSON file.

    :param results: Iterable of result objects or mappings.
    :param output_path: Target JSON file path.
    """
    data = []
    for item in results:
        serialized = _serialize_item(item)
        if serialized is not None:
            data.append(serialized)

    logger.info("Writing %d result(s) to %s", len(data), output_path)
    try:
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.error("Failed to write results to %s: %s", output_path, exc)
        raise