"""
models.py – SQLAlchemy database schema.
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Network(str, enum.Enum):
    trc20 = "trc20"
    bep20 = "bep20"


class PaymentStatus(str, enum.Enum):
    pending = "pending"
    confirming = "confirming"
    paid = "paid"
    expired = "expired"
    overpaid = "overpaid"


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Reference from the calling application
    order_id = db.Column(db.String(128), unique=True, nullable=False, index=True)

    # trc20 | bep20
    network = db.Column(db.Enum(Network), nullable=False)

    # Generated deposit address
    address = db.Column(db.String(256), nullable=False)

    # AES-encrypted private key (Fernet)
    private_key_enc = db.Column(db.Text, nullable=False)

    # Amounts (USDT)
    amount_expected = db.Column(db.Numeric(20, 6), nullable=False)
    amount_received = db.Column(db.Numeric(20, 6), default=0, nullable=False)

    # Payment lifecycle
    status = db.Column(
        db.Enum(PaymentStatus),
        default=PaymentStatus.pending,
        nullable=False,
        index=True,
    )

    # Caller's callback URL
    webhook_url = db.Column(db.String(2048), nullable=True)

    # Blockchain data
    tx_hash = db.Column(db.String(128), nullable=True)
    confirmations = db.Column(db.Integer, default=0, nullable=False)

    # Timestamps (UTC)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    def to_dict(self, include_sensitive: bool = False) -> dict:
        data = {
            "id": self.id,
            "order_id": self.order_id,
            "network": self.network.value if self.network else None,
            "address": self.address,
            "amount_expected": float(self.amount_expected),
            "amount_received": float(self.amount_received),
            "status": self.status.value if self.status else None,
            "webhook_url": self.webhook_url,
            "tx_hash": self.tx_hash,
            "confirmations": self.confirmations,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "paid_at": self.paid_at.isoformat() if self.paid_at else None,
        }
        # Private key is NEVER included in normal API responses
        return data
