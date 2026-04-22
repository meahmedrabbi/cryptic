"""
webhook.py – Fire HMAC-signed HTTP callbacks to the merchant application.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 10  # seconds


def _sign_payload(payload: bytes, secret: str) -> str:
    """Return an HMAC-SHA256 hex digest of *payload* using *secret*."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


def fire_webhook(payment) -> bool:
    """
    POST a signed JSON payload to payment.webhook_url.

    Returns True on HTTP 2xx, False otherwise.
    """
    if not payment.webhook_url:
        return False

    secret = os.environ.get("WEBHOOK_SECRET", "")

    body: dict = {
        "order_id": payment.order_id,
        "status": payment.status.value,
        "amount_expected": float(payment.amount_expected),
        "amount_received": float(payment.amount_received),
        "tx_hash": payment.tx_hash,
        "network": payment.network.value,
        "paid_at": (
            payment.paid_at.isoformat()
            if payment.paid_at
            else None
        ),
    }

    raw = json.dumps(body, separators=(",", ":")).encode()
    signature = _sign_payload(raw, secret) if secret else ""

    headers = {
        "Content-Type": "application/json",
        "X-Gateway-Signature": signature,
    }

    try:
        resp = requests.post(
            payment.webhook_url,
            data=raw,
            headers=headers,
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        logger.info(
            "Webhook delivered for order %s → %s (%s)",
            payment.order_id,
            payment.webhook_url,
            resp.status_code,
        )
        return True
    except requests.RequestException as exc:
        logger.warning(
            "Webhook failed for order %s → %s: %s",
            payment.order_id,
            payment.webhook_url,
            exc,
        )
        return False
