thonimport argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import List

from crawler.email_finder import crawl_and_collect_emails
from output.exporter import export_results

def load_settings(config_path: Path) -> dict:
    if not config_path.exists():
        logging.warning("Config file %s not found, using defaults.", config_path)
        return {}

    try:
        with config_path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        logging.error("Failed to read config file %s: %s", config_path, exc)
        return {}

def resolve_project_root() -> Path:
    # src/main.py -> src -> project_root
    return Path(__file__).resolve().parents[1]

def read_input_urls(path: Path) -> List[str]:
    if not path.exists():
        logging.error("Input URL file %s was not found.", path)
        return []

    urls: List[str] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    urls.append(line)
    except Exception as exc:
        logging.error("Failed to read input URLs from %s: %s", path, exc)
    return urls

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Email Scraper - crawl URLs and extract validated email addresses."
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to input URLs file (default: data/input_urls.txt)",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Path to output JSON file (default: from config or data/results.json)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        help="Maximum crawl depth (overrides config).",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Maximum number of concurrent HTTP requests (overrides config).",
    )
    parser.add_argument(
        "--no-dns-validation",
        action="store_true",
        help="Disable DNS validation for email domains.",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        help="HTTP proxy URL, e.g. http://user:pass@host:port (overrides config).",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO).",
    )
    return parser

async def async_main() -> None:
    project_root = resolve_project_root()
    config_path = project_root / "src" / "config" / "settings.json"

    parser = build_arg_parser()
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

    settings = load_settings(config_path)

    # Resolve paths
    input_path = Path(args.input) if args.input else project_root / "data" / "input_urls.txt"

    default_output = settings.get("output_path", "data/results.json")
    output_path = Path(args.output) if args.output else project_root / default_output

    max_depth = args.max_depth if args.max_depth is not None else int(settings.get("max_depth", 2))
    concurrency = (
        args.concurrency if args.concurrency is not None else int(settings.get("concurrency", 10))
    )
    request_timeout = float(settings.get("request_timeout", 10.0))
    dns_validation = not args.no_dns_validation and bool(settings.get("dns_validation", True))
    proxy = args.proxy if args.proxy is not None else settings.get("proxy")

    allowed_domains = settings.get("allowed_domains") or None
    if isinstance(allowed_domains, list):
        allowed_domains = set(allowed_domains)

    logging.info("Using input file: %s", input_path)
    logging.info("Using output file: %s", output_path)
    logging.info("Max depth: %d | Concurrency: %d | DNS validation: %s", max_depth, concurrency, dns_validation)

    urls = read_input_urls(input_path)
    if not urls:
        logging.error("No URLs to crawl. Please provide at least one URL in %s.", input_path)
        return

    try:
        results = await crawl_and_collect_emails(
            start_urls=urls,
            max_depth=max_depth,
            concurrency=concurrency,
            request_timeout=request_timeout,
            dns_validate=dns_validation,
            proxy=proxy,
            allowed_domains=allowed_domains,
        )
    except Exception as exc:
        logging.exception("Fatal error during crawl: %s", exc)
        return

    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        export_results(results, output_path)
        logging.info("Successfully wrote %d unique emails to %s", len(results), output_path)
    except Exception as exc:
        logging.exception("Failed to export results: %s", exc)

if __name__ == "__main__":
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        logging.warning("Interrupted by user, shutting down.")