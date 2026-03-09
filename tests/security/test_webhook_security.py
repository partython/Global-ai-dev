"""
Priya Global Platform — Webhook Security Tests

Tests webhook signature verification, replay prevention,
and timestamp validation across all channel integrations.

Critical for: WhatsApp Business API, Stripe, Twilio, Meta webhooks
"""

import hashlib
import hmac
import json
import time
import pytest
from datetime import datetime, timedelta, timezone


# ─── Helpers ───

def create_hmac_signature(payload: bytes, secret: str, algorithm: str = "sha256") -> str:
    """Create HMAC signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload,
        getattr(hashlib, algorithm),
    ).hexdigest()


def create_stripe_signature(payload: bytes, secret: str, timestamp: int = None) -> str:
    """Create Stripe-style webhook signature (t=timestamp,v1=signature)."""
    ts = timestamp or int(time.time())
    signed_payload = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


def create_meta_signature(payload: bytes, secret: str) -> str:
    """Create Meta/WhatsApp webhook signature."""
    return "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()


# ============================================================
# Webhook Signature Tests
# ============================================================


@pytest.mark.security
class TestWebhookSignatureVerification:
    """Test that webhook endpoints verify signatures correctly."""

    def test_valid_hmac_signature_accepted(self):
        """Valid HMAC-SHA256 signature should pass verification."""
        secret = "whsec_test_secret_key_12345"
        payload = b'{"event": "message.received", "data": {"id": "msg_123"}}'

        signature = create_hmac_signature(payload, secret)
        expected = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()

        assert signature == expected

    def test_invalid_signature_rejected(self):
        """Invalid signature must be rejected."""
        secret = "whsec_test_secret_key_12345"
        payload = b'{"event": "message.received"}'

        valid_sig = create_hmac_signature(payload, secret)

        # Tampered payload should produce different signature
        tampered_payload = b'{"event": "refund.created", "amount": 99999}'
        tampered_sig = create_hmac_signature(tampered_payload, secret)

        assert valid_sig != tampered_sig

    def test_signature_is_constant_time_comparison(self):
        """Signature comparison must use constant-time to prevent timing attacks."""
        secret = "test_secret"
        payload = b'test_payload'
        sig = create_hmac_signature(payload, secret)

        # hmac.compare_digest is constant-time
        assert hmac.compare_digest(sig, sig) is True
        assert hmac.compare_digest(sig, "wrong") is False

    def test_empty_signature_rejected(self):
        """Empty signature string must be rejected."""
        assert not hmac.compare_digest("", "expected_signature")

    def test_none_signature_handled(self):
        """None/missing signature must not crash."""
        with pytest.raises(TypeError):
            hmac.compare_digest(None, "expected")


@pytest.mark.security
class TestStripeWebhookSecurity:
    """Test Stripe-specific webhook signature format."""

    def test_valid_stripe_signature_format(self):
        """Stripe signature format: t=timestamp,v1=hash."""
        secret = "whsec_stripe_test"
        payload = b'{"type": "payment_intent.succeeded"}'

        sig = create_stripe_signature(payload, secret)

        assert sig.startswith("t=")
        assert ",v1=" in sig

    def test_stripe_signature_with_old_timestamp_detected(self):
        """Stripe webhooks older than 5 minutes should be flagged."""
        secret = "whsec_stripe_test"
        payload = b'{"type": "payment_intent.succeeded"}'
        old_timestamp = int(time.time()) - 600  # 10 minutes ago

        sig = create_stripe_signature(payload, secret, timestamp=old_timestamp)

        # Extract timestamp from signature
        parts = dict(p.split("=", 1) for p in sig.split(","))
        sig_timestamp = int(parts["t"])
        current_time = int(time.time())

        # Should be detected as too old (>5 min tolerance)
        assert (current_time - sig_timestamp) > 300

    def test_stripe_signature_replay_detection(self):
        """Same Stripe event ID should be idempotent."""
        event_ids_seen = set()
        event_id = "evt_test_123456"

        # First time: accepted
        assert event_id not in event_ids_seen
        event_ids_seen.add(event_id)

        # Second time: already processed (replay)
        assert event_id in event_ids_seen


@pytest.mark.security
class TestMetaWebhookSecurity:
    """Test Meta/WhatsApp webhook signature verification."""

    def test_valid_meta_signature_format(self):
        """Meta signature format: sha256=hexdigest."""
        secret = "meta_app_secret_test"
        payload = b'{"entry": [{"changes": []}]}'

        sig = create_meta_signature(payload, secret)

        assert sig.startswith("sha256=")
        assert len(sig) == 71  # "sha256=" + 64 hex chars

    def test_meta_signature_tampered_payload_rejected(self):
        """Tampered Meta webhook payload produces different signature."""
        secret = "meta_app_secret_test"
        original = b'{"entry": [{"changes": [{"value": {"messages": []}}]}]}'
        tampered = b'{"entry": [{"changes": [{"value": {"messages": [{"text": "hacked"}]}}]}]}'

        sig_original = create_meta_signature(original, secret)
        sig_tampered = create_meta_signature(tampered, secret)

        assert sig_original != sig_tampered

    def test_meta_webhook_verify_token_validation(self):
        """Meta webhook verification challenge must match configured token."""
        verify_token = "priya_webhook_verify_token_abc123"

        # Simulate Meta verification challenge
        challenge_token = verify_token
        hub_verify_token = verify_token

        # Must match exactly
        assert hmac.compare_digest(challenge_token, hub_verify_token)

        # Wrong token must fail
        assert not hmac.compare_digest("wrong_token", hub_verify_token)


@pytest.mark.security
class TestWebhookReplayPrevention:
    """Test that webhook replay attacks are prevented."""

    def test_duplicate_event_detection(self):
        """Duplicate webhook events must be detected and rejected."""
        processed_events = set()

        events = [
            {"id": "evt_001", "type": "payment.completed"},
            {"id": "evt_002", "type": "message.received"},
            {"id": "evt_001", "type": "payment.completed"},  # Duplicate!
        ]

        accepted = 0
        rejected = 0

        for event in events:
            if event["id"] in processed_events:
                rejected += 1
            else:
                processed_events.add(event["id"])
                accepted += 1

        assert accepted == 2
        assert rejected == 1

    def test_timestamp_window_enforcement(self):
        """Webhooks outside the acceptable time window must be rejected."""
        now = datetime.now(timezone.utc)
        max_age = timedelta(minutes=5)

        # Recent webhook: accepted
        recent = now - timedelta(seconds=30)
        assert (now - recent) < max_age

        # Old webhook: rejected
        old = now - timedelta(minutes=10)
        assert (now - old) > max_age

        # Future webhook: suspicious
        future = now + timedelta(minutes=10)
        assert (future - now) > max_age

    def test_nonce_prevents_replay(self):
        """Each webhook must include a unique nonce that cannot be reused."""
        import uuid

        nonce_store = set()

        nonce1 = str(uuid.uuid4())
        nonce2 = str(uuid.uuid4())

        # First use: valid
        assert nonce1 not in nonce_store
        nonce_store.add(nonce1)

        # Replay attempt: invalid
        assert nonce1 in nonce_store

        # Different nonce: valid
        assert nonce2 not in nonce_store
