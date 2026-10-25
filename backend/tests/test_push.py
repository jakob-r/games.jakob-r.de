"""Web Push endpoint checks and VAPID delivery without network."""

from __future__ import annotations

import base64
import os

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import webpush

from games_platform.core.push import (
    PushEndpointError,
    generate_vapid_keypair,
    validate_push_endpoint,
)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class _Response:
    status_code = 201
    reason = "Created"
    text = ""
    headers = None


class _Session:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        data: bytes | None = None,
        headers: object = None,
        timeout: float | None = None,
    ) -> _Response:
        stored = dict(headers) if headers is not None else {}
        self.calls.append({"url": url, "data": data, "headers": stored, "timeout": timeout})
        return _Response()


def test_webpush_signs_with_generated_vapid_key_and_topic() -> None:
    _public_key, private_key = generate_vapid_keypair()
    client_key = ec.generate_private_key(ec.SECP256R1())
    p256dh = _b64url(
        client_key.public_key().public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
    )
    session = _Session()
    endpoint = "https://fcm.googleapis.com/fcm/send/test-sub"
    webpush(
        subscription_info={
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": _b64url(os.urandom(16))},
        },
        data='{"title":"turn"}',
        vapid_private_key=private_key,
        vapid_claims={"sub": "mailto:games@jakob-r.de"},
        ttl=300,
        headers={"Topic": "turn-abc123"},
        requests_session=session,  # type: ignore[arg-type]
    )

    assert len(session.calls) == 1
    call = session.calls[0]
    assert call["url"] == endpoint
    headers = call["headers"]
    assert isinstance(headers, dict)
    lowered = {str(key).lower(): value for key, value in headers.items()}
    assert lowered["ttl"] == "300"
    assert lowered["topic"] == "turn-abc123"
    assert str(lowered["authorization"]).startswith("vapid ")


def test_validate_push_endpoint_allowlist() -> None:
    ok = "https://fcm.googleapis.com/fcm/send/abc"
    assert validate_push_endpoint(f"  {ok}  ") == ok
    assert validate_push_endpoint("https://updates.push.services.mozilla.com/wpush/v2/abc")
    assert validate_push_endpoint("https://web.push.apple.com/Q")
    assert validate_push_endpoint("https://wns2.notify.windows.com/w/?token=1")

    rejected = [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://127.0.0.1/push",
        "https://evil.example/push",
        "https://user:pass@fcm.googleapis.com/fcm/send/abc",
        "https://fcm.googleapis.com:8443/fcm/send/abc",
    ]
    for endpoint in rejected:
        with pytest.raises(PushEndpointError):
            validate_push_endpoint(endpoint)
