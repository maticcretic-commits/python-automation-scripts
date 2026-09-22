"""Offline tests for scripts/job_runner.py."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import job_runner  # noqa: E402

PYTHON = sys.executable


def test_failing_job_does_not_stop_other_jobs():
    jobs = [
        {"name": "boom", "command": f"{PYTHON} -c \"import sys; sys.exit(1)\""},
        {"name": "fine", "command": f"{PYTHON} -c \"print('hello')\""},
    ]
    results = job_runner.run_all_once(jobs)
    assert [r["name"] for r in results] == ["boom", "fine"]
    assert results[0]["ok"] is False
    assert results[0]["returncode"] == 1
    assert results[1]["ok"] is True
    assert "hello" in results[1]["stdout_tail"]


def test_missing_command_is_captured_not_raised():
    jobs = [
        {"name": "nope", "command": "definitely-not-a-real-binary-xyz"},
        {"name": "fine", "command": f"{PYTHON} -c \"print('ok')\""},
    ]
    results = job_runner.run_all_once(jobs)
    assert results[0]["ok"] is False
    assert "not found" in results[0]["error"]
    assert results[1]["ok"] is True  # runner kept going


def test_result_fields_are_populated():
    result = job_runner.run_job(
        {"name": "demo", "command": f"{PYTHON} -c \"print('x')\""})
    assert result["ok"] is True
    assert result["returncode"] == 0
    assert result["duration_seconds"] >= 0
    assert result["finished_at"]
