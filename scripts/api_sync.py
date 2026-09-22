#!/usr/bin/env python3
"""api_sync.py - sync paginated records from a REST API into a local JSON store.

Practice script demonstrating API automation: API-key auth, pagination,
retry with exponential backoff, structured logging, atomic writes.

Usage:
    export API_BASE_URL="https://api.example.com"
    export API_KEY="your-api-key"
    python3 scripts/api_sync.py --endpoint /v1/records --out data/records.json
    python3 scripts/api_sync.py --dry-run   # fetch but don't write anything

Expected page shape: {"items": [...], "next_page": <int|null>}
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone

import requests


# ---------------------------------------------------------------------------
# Structured logging: one JSON object per line on stderr
# ---------------------------------------------------------------------------

class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": record.getMessage(),
            }
        )


def get_logger(name: str = "api_sync") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(JsonLogFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


log = get_logger()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class SyncError(Exception):
    """Fatal sync failure: retry budget exhausted, auth error, bad payload."""


class TransientHTTPError(Exception):
    def __init__(self, status_code: int):
        super().__init__(f"transient HTTP {status_code}")
        self.status_code = status_code


RETRYABLE_STATUS = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# HTTP helpers (requester is injectable so tests run without network)
# ---------------------------------------------------------------------------

def request_with_retry(requester, method: str, url: str,
                       max_retries: int = 3, backoff_seconds: float = 1.0,
                       **kwargs):
    """Call ``requester(method, url, **kwargs)`` with exponential-backoff retries.

    Retries HTTP 429/5xx and connection-level errors. Fails fast (SyncError) on
    other HTTP errors, e.g. 401/404. Raises SyncError when the retry budget
    is exhausted.
    """
    attempt = 0
    while True:
        error = None
        try:
            resp = requester(method, url, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            error = exc
        else:
            status = getattr(resp, "status_code", None)
            if status in RETRYABLE_STATUS:
                error = TransientHTTPError(status)
            else:
                try:
                    resp.raise_for_status()
                except Exception as exc:
                    raise SyncError(f"HTTP {status}: not retryable, giving up") from exc
                return resp
        if attempt >= max_retries:
            raise SyncError(
                f"retry budget exhausted for {method} {url} "
                f"after {max_retries} retries: {error}"
            )
        wait = backoff_seconds * (2 ** attempt)
        log.info("transient failure (attempt %d/%d): %s - retrying in %.1fs",
                 attempt + 1, max_retries + 1, error, wait)
        time.sleep(wait)
        attempt += 1


def fetch_all_records(base_url: str, endpoint: str, api_key: str,
                      max_retries: int = 3, backoff_seconds: float = 1.0,
                      page_size: int = 100, requester=None) -> list:
    """Fetch every page from the API. Returns the concatenated item list."""
    requester = requester or requests.request
    url = base_url.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}
    items: list = []
    page = 1
    while True:
        resp = request_with_retry(
            requester, "GET", url,
            max_retries=max_retries, backoff_seconds=backoff_seconds,
            headers=headers, params={"page": page, "page_size": page_size},
            timeout=30,
        )
        payload = resp.json()
        if not isinstance(payload, dict) or "items" not in payload:
            raise SyncError(f"unexpected payload shape on page {page}")
        batch = payload["items"]
        if not isinstance(batch, list):
            raise SyncError(f"'items' is not a list on page {page}")
        items.extend(batch)
        log.info("fetched page %d (%d records, %d total)", page, len(batch), len(items))
        page = payload.get("next_page")
        if page is None:
            break
    return items


def sync(base_url: str, endpoint: str, api_key: str, out_path: str,
         dry_run: bool = False, max_retries: int = 3,
         backoff_seconds: float = 1.0, page_size: int = 100,
         requester=None) -> list:
    """Fetch all records; write them atomically unless dry_run is set."""
    items = fetch_all_records(
        base_url, endpoint, api_key,
        max_retries=max_retries, backoff_seconds=backoff_seconds,
        page_size=page_size, requester=requester,
    )
    log.info("sync complete: %d records (dry_run=%s)", len(items), dry_run)
    if dry_run:
        return items
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
    tmp_path = out_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as fh:
        json.dump(
            {
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "count": len(items),
                "items": items,
            },
            fh, indent=2,
        )
    os.replace(tmp_path, out_path)  # atomic: no half-written file on crash
    log.info("wrote %s", out_path)
    return items


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Sync a paginated REST API to JSON.")
    parser.add_argument("--endpoint", default="/v1/records")
    parser.add_argument("--out", default="data/records.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="fetch everything but write no file")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument("--backoff", type=float, default=1.0,
                        help="base backoff seconds (doubles each retry)")
    parser.add_argument("--page-size", type=int, default=100)
    args = parser.parse_args(argv)

    base_url = os.environ.get("API_BASE_URL", "").strip()
    api_key = os.environ.get("API_KEY", "").strip()
    if not base_url or not api_key:
        print("error: set API_BASE_URL and API_KEY env vars (see .env.example)",
              file=sys.stderr)
        return 2
    try:
        items = sync(base_url, args.endpoint, api_key, args.out,
                     dry_run=args.dry_run, max_retries=args.max_retries,
                     backoff_seconds=args.backoff, page_size=args.page_size)
    except SyncError as exc:
        log.error("sync failed: %s", exc)
        return 1
    print(f"synced {len(items)} records" + (" (dry run)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
