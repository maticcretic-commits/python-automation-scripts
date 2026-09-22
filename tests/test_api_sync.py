"""Offline tests for scripts/api_sync.py. The HTTP layer is mocked; no network."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import api_sync  # noqa: E402


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if 400 <= self.status_code < 600:
            raise Exception(f"HTTP {self.status_code}")


def make_requester(responses):
    """Return a requester that pops FakeResponses off the list; count calls."""
    calls = []

    def requester(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return responses.pop(0)

    requester.calls = calls
    return requester


def page(items, next_page=None):
    return FakeResponse(200, {"items": items, "next_page": next_page})


def test_retries_transient_error_then_succeeds():
    requester = make_requester([
        FakeResponse(503), FakeResponse(500), page([{"id": 1}]),
    ])
    items = api_sync.fetch_all_records(
        "https://api.example.com", "/v1/records", "key",
        max_retries=3, backoff_seconds=0, requester=requester,
    )
    assert items == [{"id": 1}]
    assert len(requester.calls) == 3


def test_pagination_follows_next_page():
    requester = make_requester([
        page([{"id": 1}, {"id": 2}], next_page=2),
        page([{"id": 3}]),
    ])
    items = api_sync.fetch_all_records(
        "https://api.example.com", "/v1/records", "key",
        max_retries=2, backoff_seconds=0, requester=requester,
    )
    assert [r["id"] for r in items] == [1, 2, 3]
    # second call must carry page=2
    assert requester.calls[1][2]["params"]["page"] == 2


def test_retry_budget_exhausted_raises_sync_error():
    requester = make_requester([FakeResponse(503)] * 5)
    try:
        api_sync.fetch_all_records(
            "https://api.example.com", "/v1/records", "key",
            max_retries=2, backoff_seconds=0, requester=requester,
        )
    except api_sync.SyncError:
        pass
    else:
        raise AssertionError("expected SyncError")
    assert len(requester.calls) == 3  # initial + 2 retries


def test_dry_run_fetches_but_writes_nothing(tmp_path):
    requester = make_requester([page([{"id": 1}, {"id": 2}])])
    out = str(tmp_path / "records.json")
    items = api_sync.sync(
        "https://api.example.com", "/v1/records", "key", out,
        dry_run=True, max_retries=1, backoff_seconds=0, requester=requester,
    )
    assert len(items) == 2
    assert not os.path.exists(out)
