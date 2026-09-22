"""Offline tests for scripts/csv_transform.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import csv_transform  # noqa: E402

RULES = {
    "normalize_headers": True,
    "column_mapping": {
        "Customer ID": "id",
        "Customer Name": "name",
        "E-mail": "email",
        "Signup Date": "signup_date",
    },
    "date_columns": ["signup_date"],
    "email_columns": ["email"],
    "required_columns": ["email"],
    "output_columns": ["id", "name", "email", "signup_date"],
}


def test_mapping_and_date_parsing():
    rows = [{"Customer ID": "1", "Customer Name": " Alice ",
             "E-mail": "alice@example.com", "Signup Date": "15/02/2024"}]
    clean, quarantined = csv_transform.transform_rows(rows, RULES)
    assert quarantined == []
    assert clean == [{"id": "1", "name": "Alice",
                      "email": "alice@example.com", "signup_date": "2024-02-15"}]


def test_missing_required_column_is_quarantined():
    rows = [{"Customer ID": "3", "Customer Name": "Carol",
             "E-mail": "", "Signup Date": "2024-03-01"}]
    clean, quarantined = csv_transform.transform_rows(rows, RULES)
    assert clean == []
    assert len(quarantined) == 1
    assert "missing required column 'email'" in quarantined[0]["quarantine_reason"]


def test_bad_date_is_quarantined():
    rows = [{"Customer ID": "4", "Customer Name": "Dan",
             "E-mail": "dan@example.com", "Signup Date": "not-a-date"}]
    clean, quarantined = csv_transform.transform_rows(rows, RULES)
    assert clean == []
    assert "unparseable date" in quarantined[0]["quarantine_reason"]


def test_bad_email_is_quarantined():
    rows = [{"Customer ID": "2", "Customer Name": "Bob",
             "E-mail": "bob-at-example.com", "Signup Date": "2024-01-01"}]
    clean, quarantined = csv_transform.transform_rows(rows, RULES)
    assert clean == []
    assert "invalid email" in quarantined[0]["quarantine_reason"]


def test_various_date_formats_parse_to_iso():
    assert csv_transform.parse_date("2024-01-15") == "2024-01-15"
    assert csv_transform.parse_date("2024/04/10") == "2024-04-10"
    assert csv_transform.parse_date("15/02/2024") == "2024-02-15"
    assert csv_transform.parse_date("garbage") is None
    assert csv_transform.parse_date("") is None
