#!/usr/bin/env python3
"""csv_transform.py - normalize messy CSVs using rules from a JSON config.

Practice script demonstrating data-cleaning automation: header normalization,
column renaming via mapping, date parsing, email sanity checks, and
quarantining bad rows (with a reason) instead of silently dropping them.

Usage:
    python3 scripts/csv_transform.py data/sample_messy.csv \\
        --rules config.example.json \\
        --out data/sample_clean.csv \\
        --quarantine data/sample_quarantine.csv

Rules shape (the "csv_transform" section of config.example.json):
    {
      "normalize_headers": true,
      "column_mapping": {"Customer ID": "id"},
      "date_columns": ["signup_date"],
      "email_columns": ["email"],
      "required_columns": ["email"],
      "output_columns": ["id", "name", "email", "signup_date"]  # optional order
    }
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime

DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y-%m-%dT%H:%M:%S",
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def load_rules(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    # Accept either the full config file (with a "csv_transform" section)
    # or a rules-only file.
    return config.get("csv_transform", config)


def normalize_header(header: str) -> str:
    return header.strip().lower().replace(" ", "_")


def parse_date(value: str) -> str | None:
    """Parse a date string into ISO YYYY-MM-DD, or None if unparseable."""
    value = (value or "").strip()
    if not value:
        return None
    try:  # handles "2024-01-15" and full ISO datetimes
        return datetime.fromisoformat(value).date().isoformat()
    except ValueError:
        pass
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match((value or "").strip()))


def transform_rows(rows: list[dict], rules: dict) -> tuple[list[dict], list[dict]]:
    """Return (clean_rows, quarantined_rows).

    Each quarantined row is the mapped row plus a "quarantine_reason" key.
    """
    mapping = rules.get("column_mapping", {})
    normalize = rules.get("normalize_headers", True)
    date_cols = set(rules.get("date_columns", []))
    email_cols = set(rules.get("email_columns", []))
    required = set(rules.get("required_columns", []))
    output_cols = rules.get("output_columns")

    clean, quarantined = [], []
    for lineno, raw in enumerate(rows, start=2):  # line 1 is the header
        mapped: dict = {}
        for header, value in raw.items():
            key = normalize_header(header) if normalize else header
            mapped[mapping.get(header, mapping.get(key, key))] = (value or "").strip()

        reasons: list[str] = []
        for col in required:
            if not mapped.get(col):
                reasons.append(f"line {lineno}: missing required column '{col}'")
        for col in date_cols:
            if mapped.get(col):
                parsed = parse_date(mapped[col])
                if parsed is None:
                    reasons.append(
                        f"line {lineno}: unparseable date in '{col}': {mapped[col]!r}"
                    )
                else:
                    mapped[col] = parsed
        for col in email_cols:
            if mapped.get(col) and not looks_like_email(mapped[col]):
                reasons.append(
                    f"line {lineno}: invalid email in '{col}': {mapped[col]!r}"
                )

        if reasons:
            mapped["quarantine_reason"] = "; ".join(reasons)
            quarantined.append(mapped)
        else:
            if output_cols:
                mapped = {c: mapped.get(c, "") for c in output_cols}
            clean.append(mapped)
    return clean, quarantined


def run(input_path: str, rules_path: str, output_path: str,
        quarantine_path: str) -> tuple[int, int]:
    rules = load_rules(rules_path)
    with open(input_path, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    clean, quarantined = transform_rows(rows, rules)

    output_cols = rules.get("output_columns") or (
        list(clean[0].keys()) if clean else []
    )
    with open(output_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=output_cols)
        writer.writeheader()
        writer.writerows(clean)

    if quarantined:
        q_cols = sorted({k for row in quarantined for k in row})
        if "quarantine_reason" in q_cols:  # keep the reason column last
            q_cols = [c for c in q_cols if c != "quarantine_reason"] + ["quarantine_reason"]
        with open(quarantine_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=q_cols)
            writer.writeheader()
            writer.writerows(quarantined)
    print(f"clean: {len(clean)} rows -> {output_path}; "
          f"quarantined: {len(quarantined)} rows -> {quarantine_path}")
    return len(clean), len(quarantined)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Normalize a messy CSV.")
    parser.add_argument("input", help="input CSV path")
    parser.add_argument("--rules", default="config.example.json",
                        help="JSON config file (or its csv_transform section)")
    parser.add_argument("--out", default="data/clean.csv")
    parser.add_argument("--quarantine", default="data/quarantine.csv")
    args = parser.parse_args(argv)
    try:
        run(args.input, args.rules, args.out, args.quarantine)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
