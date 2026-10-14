#!/usr/bin/env python3
"""Conservative, unauthenticated link audit for JSON resource catalogs."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, build_opener

USER_AGENT = "VEC-Resource-Link-Audit/1.0 (public-link-check; no-auth)"
DEFAULT_URL_KEYS = ("url", "href", "public_link", "link")


def load_items(path: Path, items_key: str | None) -> list[Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Cannot read JSON catalog {path}: {error}") from error
    if items_key:
        if not isinstance(data, dict) or not isinstance(data.get(items_key), list):
            raise ValueError(f"Expected a list at JSON key {items_key!r}")
        data = data[items_key]
    if not isinstance(data, list):
        raise ValueError("Catalog must be a top-level JSON list or use --items-key")
    return data


def get_entry(item: Any, url_key: str | None) -> tuple[str, str]:
    if isinstance(item, str):
        return item, item
    if not isinstance(item, dict):
        return "", "invalid entry"
    keys = (url_key,) if url_key else DEFAULT_URL_KEYS
    url = next((item.get(key) for key in keys if isinstance(item.get(key), str)), "")
    title = item.get("title") or item.get("name") or url or "untitled"
    return str(url).strip(), str(title).strip()


def safe_display_url(url: str) -> str:
    """Remove credentials, query values, and fragments before writing reports."""
    try:
        parts = urlsplit(url)
        hostname = parts.hostname or ""
        if parts.port:
            hostname = f"{hostname}:{parts.port}"
        display = urlunsplit((parts.scheme, hostname, parts.path, "", ""))
        if parts.query:
            display += "?[query redacted]"
        if parts.fragment:
            display += "#[fragment omitted]"
        return display
    except ValueError:
        return "[invalid URL]"


def response_for(url: str, method: str, timeout: float) -> tuple[int | None, str, str | None]:
    request = Request(
        url,
        method=method,
        headers={"User-Agent": USER_AGENT, "Range": "bytes=0-0"} if method == "GET"
        else {"User-Agent": USER_AGENT},
    )
    opener = build_opener()
    try:
        with opener.open(request, timeout=timeout) as response:
            return int(response.status), response.geturl(), None
    except HTTPError as error:
        final_url = error.geturl()
        error.close()
        return int(error.code), final_url, None
    except (URLError, TimeoutError, OSError) as error:
        reason = error.reason if isinstance(error, URLError) else error
        return None, url, type(reason).__name__


def classify(status: int | None, error: str | None) -> str:
    if status is None:
        return "network_error"
    if 200 <= status < 300:
        return "ok"
    if status in (404, 410):
        return "missing"
    if status in (401, 403):
        return "access_restricted"
    if status == 429:
        return "rate_limited"
    if 500 <= status < 600:
        return "server_error"
    return "http_error"


def check_one(row: dict[str, Any], timeout: float, pause: float) -> dict[str, Any]:
    time.sleep(pause)
    url = row["raw_url"]
    result = {key: row[key] for key in ("index", "title")}
    result["url"] = safe_display_url(url)
    result["final_url"] = ""
    result["status"] = ""
    result["http_status"] = None
    result["note"] = ""
    try:
        parts = urlsplit(url)
    except ValueError:
        result["status"] = "invalid_url"
        result["note"] = "URL could not be parsed."
        return result
    if parts.scheme.lower() not in ("http", "https"):
        result["status"] = "unsupported_scheme" if parts.scheme else "invalid_url"
        result["note"] = "Only absolute HTTP(S) URLs are checked."
        return result
    if not parts.hostname:
        result["status"] = "invalid_url"
        result["note"] = "URL has no hostname."
        return result

    try:
        status, final_url, error = response_for(url, "HEAD", timeout)
        if status in (405, 501):
            status, final_url, error = response_for(url, "GET", timeout)
            result["note"] = "Server did not support HEAD; tried a byte-range GET."
    except ValueError:
        result["status"] = "invalid_url"
        result["note"] = "URL could not be requested."
        return result
    result["http_status"] = status
    result["final_url"] = safe_display_url(final_url)
    result["status"] = classify(status, error)
    if error:
        result["note"] = f"Request failed: {error}."
    elif result["status"] == "access_restricted":
        result["note"] = "May work in a browser; check manually."
    elif result["status"] == "rate_limited":
        result["note"] = "Not retried; check manually later."
    elif result["status"] == "server_error":
        result["note"] = "Temporary server failure is possible; check manually later."
    elif status is not None and 200 <= status < 300 and final_url != url:
        result["status"] = "redirected"
    elif result["status"] == "http_error":
        result["note"] = "Review response manually; it is not classified as a missing page."
    return result


def make_markdown(results: list[dict[str, Any]], checked_at: str) -> str:
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = [
        "# VEC Resource Link Audit",
        "",
        f"Checked at {checked_at}. This is a conservative unauthenticated link check, not a content review.",
        "",
        f"Entries checked: **{len(results)}**",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in sorted(counts.items()):
        lines.append(f"| {status} | {count} |")
    lines.extend([
        "",
        "Only 404/410 responses are classified as clearly missing. Access restrictions, rate limits, server errors, and network errors need manual review.",
        "",
        "| # | Resource | Status | HTTP | URL | Final URL | Note |",
        "| ---: | --- | --- | ---: | --- | --- | --- |",
    ])
    for row in results:
        lines.append(
            f"| {row['index']} | {row['title'].replace('|', '/')} | {row['status']} | "
            f"{row['http_status'] if row['http_status'] is not None else ''} | "
            f"{row['url']} | {row['final_url']} | {row['note'].replace('|', '/')} |"
        )
    lines.extend(["", "Report URLs redact query values and omit fragments. Review every flagged entry before editing the source catalog.", ""])
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit public HTTP(S) links in a JSON resource catalog.")
    parser.add_argument("catalog", type=Path, help="JSON list of resource objects")
    parser.add_argument("--items-key", help="key containing the resource list in a JSON object")
    parser.add_argument("--url-key", help="field containing each URL; otherwise common keys are detected")
    parser.add_argument("--out", type=Path, default=Path("link-audit"), help="output directory")
    parser.add_argument("--workers", type=int, default=3, help="concurrent requests, from 1 through 8 (default: 3)")
    parser.add_argument("--timeout", type=float, default=12.0, help="per-request timeout in seconds")
    parser.add_argument("--pause", type=float, default=0.2, help="pause before each URL check in seconds")
    parser.add_argument("--strict", action="store_true",
                        help="exit nonzero if a URL is clearly missing or malformed")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be from 1 through 8")
    if args.timeout <= 0 or args.pause < 0:
        parser.error("--timeout must be positive and --pause cannot be negative")
    try:
        items = load_items(args.catalog, args.items_key)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2

    rows = []
    for index, item in enumerate(items, start=1):
        url, title = get_entry(item, args.url_key)
        rows.append({"index": index, "title": title, "raw_url": url})
    checked_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda row: check_one(row, args.timeout, args.pause), rows))

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "link-audit.json").write_text(
        json.dumps({"checked_at": checked_at, "results": results}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    with (args.out / "link-audit.csv").open("w", encoding="utf-8", newline="") as handle:
        fields = ["index", "title", "status", "http_status", "url", "final_url", "note"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in results)
    (args.out / "link-audit.md").write_text(make_markdown(results, checked_at), encoding="utf-8")
    counts: dict[str, int] = {}
    for row in results:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    print(f"Audited {len(results)} URLs; status counts: {json.dumps(counts, sort_keys=True)}")
    if args.strict and any(row["status"] in ("missing", "invalid_url") for row in results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
