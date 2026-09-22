#!/usr/bin/env python3
"""webhook_receiver.py - minimal stdlib webhook receiver with HMAC verification.

Practice script demonstrating webhook automation: receive POSTed events,
verify the sender with an HMAC-SHA256 signature header, and append accepted
events to a JSONL log. Standard library only.

Usage:
    export WEBHOOK_SECRET="a-long-random-string"
    python3 scripts/webhook_receiver.py --port 8000 --log-file data/webhooks.jsonl

Senders sign the raw request body:
    X-Signature: sha256=<hex(hmac_sha256(secret, body))>
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer


def verify_signature(payload: bytes, signature_header: str | None,
                     secret: str) -> bool:
    """Check an ``X-Signature: sha256=<hex>`` header against the payload.

    Returns False for missing/malformed headers and wrong secrets.
    Uses hmac.compare_digest to avoid timing leaks.
    """
    if not signature_header or not secret:
        return False
    try:
        algo, _, provided = signature_header.partition(":")
        if algo.strip().lower() != "sha256" or not provided.strip():
            return False
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, provided.strip())
    except Exception:
        return False


class WebhookHandler(BaseHTTPRequestHandler):
    secret: str = ""
    log_path: str = "data/webhooks.jsonl"

    def log_message(self, fmt, *args):  # quieter than the default stderr chatter
        sys.stderr.write("webhook: " + fmt % args + "\n")

    def _respond(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):  # noqa: N802 - http.server naming convention
        length = int(self.headers.get("Content-Length", 0) or 0)
        payload = self.rfile.read(length) if length else b""
        if not verify_signature(payload, self.headers.get("X-Signature"), self.secret):
            self._respond(401, {"ok": False, "error": "invalid signature"})
            return
        try:
            event = json.loads(payload.decode("utf-8")) if payload else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._respond(400, {"ok": False, "error": "body is not valid JSON"})
            return
        record = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "path": self.path,
            "event": event,
        }
        os.makedirs(os.path.dirname(os.path.abspath(self.log_path)) or ".",
                    exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        self._respond(200, {"ok": True})


def run_server(port: int, secret: str, log_path: str) -> None:
    WebhookHandler.secret = secret
    WebhookHandler.log_path = log_path
    server = HTTPServer(("127.0.0.1", port), WebhookHandler)
    print(f"listening on http://127.0.0.1:{port}/webhook "
          f"(events -> {log_path}); Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Receive HMAC-signed webhooks.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-file", default="data/webhooks.jsonl")
    args = parser.parse_args(argv)
    secret = os.environ.get("WEBHOOK_SECRET", "").strip()
    if not secret:
        print("error: set the WEBHOOK_SECRET env var (see .env.example)",
              file=sys.stderr)
        return 2
    run_server(args.port, secret, args.log_file)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
