"""
monitor.py – Background job that polls blockchain APIs every N seconds and
updates payment statuses in the database.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from decimal import Decimal

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# TRC-20 polling (TronGrid REST API)
# ---------------------------------------------------------------------------

_TRONGRID_BASE = "https://api.trongrid.io"


def _trc20_get_transfers(address: str, contract: str, api_key: str) -> list[dict]:
    """
    Return TRC-20 transfer events *to* *address* for the given contract.
    Uses the TronGrid v1 accounts/{address}/transactions/trc20 endpoint.
    """
    url = f"{_TRONGRID_BASE}/v1/accounts/{address}/transactions/trc20"
    params = {
        "contract_address": contract,
        "only_to": "true",
        "limit": 20,
    }
    headers = {}
    if api_key:
        headers["TRON-PRO-API-KEY"] = api_key

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        return resp.json().get("data", [])
    except requests.RequestException as exc:
        logger.warning("TronGrid request failed for %s: %s", address, exc)
        return []


def check_trc20_payment(payment, app_config: dict) -> None:
    """Update a pending TRC-20 payment record by querying TronGrid."""
    from models import PaymentStatus, db

    contract = app_config.get(
        "USDT_TRC20_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    )
    api_key = app_config.get("TRONGRID_API_KEY", "")
    required_conf = int(app_config.get("TRC20_CONFIRMATIONS", 20))

    transfers = _trc20_get_transfers(payment.address, contract, api_key)

    for tx in transfers:
        try:
            value = Decimal(tx.get("value", "0")) / Decimal("1_000_000")  # 6 decimals
            tx_hash = tx.get("transaction_id", "")
            confirmed = tx.get("confirmed", False)
            block_ts = tx.get("block_timestamp", 0)  # ms epoch

            if value <= 0:
                continue

            payment.amount_received = value
            payment.tx_hash = tx_hash

            # Tron's v1 API marks the tx as confirmed after enough blocks
            if confirmed:
                payment.confirmations = required_conf
                if value >= payment.amount_expected:
                    payment.status = (
                        PaymentStatus.overpaid
                        if value > payment.amount_expected
                        else PaymentStatus.paid
                    )
                    payment.paid_at = datetime.now(timezone.utc)
                else:
                    # Partial – stay confirming until expired
                    payment.status = PaymentStatus.confirming
            else:
                payment.status = PaymentStatus.confirming
                payment.confirmations = 0

            db.session.commit()
            break  # first matching tx wins

        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing TRC-20 tx for order %s: %s", payment.order_id, exc)
            db.session.rollback()


# ---------------------------------------------------------------------------
# BEP-20 polling (BSCScan API)
# ---------------------------------------------------------------------------

_BSCSCAN_BASE = "https://api.bscscan.com/api"


def _bep20_get_transfers(address: str, contract: str, api_key: str) -> list[dict]:
    """Return BEP-20 token transfers to *address* from BSCScan."""
    params = {
        "module": "account",
        "action": "tokentx",
        "contractaddress": contract,
        "address": address,
        "sort": "desc",
        "apikey": api_key or "YourApiKeyToken",
    }
    try:
        resp = requests.get(_BSCSCAN_BASE, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1":
            return data.get("result", [])
        return []
    except requests.RequestException as exc:
        logger.warning("BSCScan request failed for %s: %s", address, exc)
        return []


def _bep20_get_block_number(api_key: str) -> int:
    """Return the latest BSC block number."""
    params = {
        "module": "proxy",
        "action": "eth_blockNumber",
        "apikey": api_key or "YourApiKeyToken",
    }
    try:
        resp = requests.get(_BSCSCAN_BASE, params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json().get("result", "0x0")
        return int(result, 16)
    except Exception:  # noqa: BLE001
        return 0


def check_bep20_payment(payment, app_config: dict) -> None:
    """Update a pending BEP-20 payment record by querying BSCScan."""
    from models import PaymentStatus, db

    contract = app_config.get(
        "USDT_BEP20_CONTRACT", "0x55d398326f99059fF775485246999027B3197955"
    )
    api_key = app_config.get("BSCSCAN_API_KEY", "")
    required_conf = int(app_config.get("BEP20_CONFIRMATIONS", 12))

    transfers = _bep20_get_transfers(
        payment.address.lower(), contract.lower(), api_key
    )
    latest_block = _bep20_get_block_number(api_key)

    for tx in transfers:
        try:
            # USDT on BSC has 18 decimals
            value = Decimal(tx.get("value", "0")) / Decimal("10") ** 18
            tx_hash = tx.get("hash", "")
            tx_block = int(tx.get("blockNumber", 0))
            to_addr = tx.get("to", "").lower()

            if to_addr != payment.address.lower():
                continue
            if value <= 0:
                continue

            confs = (latest_block - tx_block) if latest_block >= tx_block else 0
            payment.amount_received = value
            payment.tx_hash = tx_hash
            payment.confirmations = confs

            if confs >= required_conf:
                if value >= payment.amount_expected:
                    payment.status = (
                        PaymentStatus.overpaid
                        if value > payment.amount_expected
                        else PaymentStatus.paid
                    )
                    payment.paid_at = datetime.now(timezone.utc)
                else:
                    payment.status = PaymentStatus.confirming
            else:
                payment.status = PaymentStatus.confirming

            db.session.commit()
            break

        except Exception as exc:  # noqa: BLE001
            logger.error("Error processing BEP-20 tx for order %s: %s", payment.order_id, exc)
            db.session.rollback()


# ---------------------------------------------------------------------------
# Expiry sweep
# ---------------------------------------------------------------------------

def expire_old_payments(app_config: dict) -> None:
    """Mark all pending/confirming payments past their expiry as expired."""
    from models import Payment, PaymentStatus, db

    now = datetime.now(timezone.utc)
    expired = (
        Payment.query.filter(
            Payment.status.in_([PaymentStatus.pending, PaymentStatus.confirming]),
            Payment.expires_at < now,
        ).all()
    )
    for p in expired:
        p.status = PaymentStatus.expired
    if expired:
        db.session.commit()
        logger.info("Expired %d unpaid invoice(s).", len(expired))


# ---------------------------------------------------------------------------
# Main poll loop (called by APScheduler)
# ---------------------------------------------------------------------------

def poll_payments(app) -> None:
    """
    Check all open payments.  Must be called within an application context
    because we use SQLAlchemy models.
    """
    with app.app_context():
        from models import Network, Payment, PaymentStatus, db
        from webhook import fire_webhook

        cfg = app.config

        # First sweep expired invoices
        expire_old_payments(cfg)

        open_payments = Payment.query.filter(
            Payment.status.in_([PaymentStatus.pending, PaymentStatus.confirming])
        ).all()

        for payment in open_payments:
            try:
                if payment.network == Network.trc20:
                    check_trc20_payment(payment, cfg)
                elif payment.network == Network.bep20:
                    check_bep20_payment(payment, cfg)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Unhandled error while polling order %s: %s",
                    payment.order_id,
                    exc,
                )

        # Fire webhooks for newly finalised payments
        finalized = Payment.query.filter(
            Payment.status.in_(
                [PaymentStatus.paid, PaymentStatus.overpaid, PaymentStatus.expired]
            ),
            Payment.webhook_url.isnot(None),
        ).all()

        for payment in finalized:
            # Only fire once: clear the URL after successful delivery
            if fire_webhook(payment):
                payment.webhook_url = None
        db.session.commit()
