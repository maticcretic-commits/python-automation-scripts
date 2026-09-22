#!/usr/bin/env python3
"""job_runner.py - tiny scheduled-job runner with failure isolation.

Practice script demonstrating automation orchestration: jobs declared in a
JSON config, subprocess execution with timeouts, per-job result logging,
and - critically - a crashing job never stops the other jobs.

Usage:
    python3 scripts/job_runner.py --config config.example.json --once
    python3 scripts/job_runner.py --config config.example.json --loop --cycles 2

Config shape (the "jobs" section of config.example.json):
    {
      "jobs": [
        {"name": "csv-cleanup", "command": "python3 scripts/csv_transform.py ...",
         "interval_seconds": 3600, "timeout_seconds": 120}
      ],
      "default_timeout_seconds": 300
    }
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone


def load_jobs(config_path: str) -> tuple[list[dict], float]:
    with open(config_path, encoding="utf-8") as fh:
        config = json.load(fh)
    jobs = config.get("jobs", [])
    default_timeout = float(config.get("default_timeout_seconds", 300))
    return jobs, default_timeout


def run_job(job: dict, default_timeout: float = 300.0) -> dict:
    """Run one job. Never raises for job-level failures; returns a result dict."""
    name = job.get("name", "<unnamed>")
    command = job.get("command", "")
    timeout = float(job.get("timeout_seconds", default_timeout))
    started = time.monotonic()
    result = {
        "name": name,
        "command": command,
        "ok": False,
        "returncode": None,
        "duration_seconds": 0.0,
        "stdout_tail": "",
        "error": "",
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        proc = subprocess.run(
            shlex.split(command),
            capture_output=True, text=True, timeout=timeout,
        )
        result["returncode"] = proc.returncode
        result["stdout_tail"] = proc.stdout[-2000:]
        result["ok"] = proc.returncode == 0
        if not result["ok"]:
            result["error"] = (proc.stderr or f"exit code {proc.returncode}")[-2000:]
    except FileNotFoundError as exc:
        result["error"] = f"command not found: {exc}"
    except subprocess.TimeoutExpired:
        result["error"] = f"timed out after {timeout}s"
    except Exception as exc:  # noqa: BLE001 - a job must never kill the runner
        result["error"] = f"unexpected error: {exc!r}"
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    print(json.dumps({"event": "job_result", **result}), flush=True)
    return result


def run_all_once(jobs: list[dict], default_timeout: float = 300.0) -> list[dict]:
    """Run every job once, in order. One job's failure never stops the rest."""
    results = []
    for job in jobs:
        try:
            results.append(run_job(job, default_timeout))
        except Exception as exc:  # noqa: BLE001 - belt and suspenders
            results.append({
                "name": job.get("name", "<unnamed>"), "ok": False,
                "error": f"runner-level error: {exc!r}",
            })
    return results


def run_loop(jobs: list[dict], default_timeout: float = 300.0,
             cycles: int | None = None, sleep_fn=time.sleep) -> None:
    """Repeat jobs on their intervals. cycles=None loops forever."""
    last_run: dict[str, float] = {}
    completed_cycles = 0
    while True:
        now = time.monotonic()
        for job in jobs:
            interval = float(job.get("interval_seconds", 60))
            if now - last_run.get(job.get("name", ""), 0) >= interval:
                run_job(job, default_timeout)
                last_run[job.get("name", "")] = time.monotonic()
        completed_cycles += 1
        if cycles is not None and completed_cycles >= cycles:
            break
        sleep_fn(1)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Run scheduled jobs from config.")
    parser.add_argument("--config", default="config.example.json")
    parser.add_argument("--once", action="store_true",
                        help="run every job exactly once and exit (default)")
    parser.add_argument("--loop", action="store_true",
                        help="repeat jobs on their intervals")
    parser.add_argument("--cycles", type=int, default=None,
                        help="with --loop, stop after N cycles (demo/testing)")
    args = parser.parse_args(argv)
    try:
        jobs, default_timeout = load_jobs(args.config)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot load config: {exc}", file=sys.stderr)
        return 1
    if args.loop:
        run_loop(jobs, default_timeout, cycles=args.cycles)
    else:
        results = run_all_once(jobs, default_timeout)
        failed = [r["name"] for r in results if not r["ok"]]
        print(f"{len(results) - len(failed)}/{len(results)} jobs ok"
              + (f"; failed: {', '.join(failed)}" if failed else ""))
        return 1 if failed else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
