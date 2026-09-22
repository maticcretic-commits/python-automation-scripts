"""Offline tests for scripts/webhook_receiver.py.

verify_signature is tested directly - no live server needed.
"""
import hashlib
import hmac
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import webhook_receiver  # noqa: E402

SECRET = "test-secret-123"
PAYLOAD = b'{"event":"demo","id":7}'


def sign(payload: bytes, secret: str) -> str:
    return "sha256:" + hmac.new(secret.encode(), payload,
                                hashlib.sha256).hexdigest()


def test_valid_signature_accepted():
    assert webhook_receiver.verify_signature(PAYLOAD, sign(PAYLOAD, SECRET),
                                             SECRET) is True


def test_wrong_secret_rejected():
    assert webhook_receiver.verify_signature(PAYLOAD, sign(PAYLOAD, SECRET),
                                             "other-secret") is False


def test_tampered_payload_rejected():
    assert webhook_receiver.verify_signature(b'{"event":"evil"}',
                                             sign(PAYLOAD, SECRET),
                                             SECRET) is False


def test_malformed_header_rejected():
    assert webhook_receiver.verify_signature(PAYLOAD, "not-a-signature",
                                             SECRET) is False
    assert webhook_receiver.verify_signature(PAYLOAD, "md5:abcdef", SECRET) is False


def test_missing_header_rejected():
    assert webhook_receiver.verify_signature(PAYLOAD, None, SECRET) is False
    assert webhook_receiver.verify_signature(PAYLOAD, "", SECRET) is False
