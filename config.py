"""
config.py – All application settings, loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ------------------------------------------------------------------
    # Flask
    # ------------------------------------------------------------------
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "change-me-in-production")
    DEBUG: bool = os.environ.get("FLASK_DEBUG", "false").lower() == "true"

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL", "sqlite:///gateway.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # ------------------------------------------------------------------
    # Encryption
    # ------------------------------------------------------------------
    # 32-byte URL-safe base64-encoded key generated with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY", "")

    # ------------------------------------------------------------------
    # Admin authentication
    # ------------------------------------------------------------------
    ADMIN_TOKEN: str = os.environ.get("ADMIN_TOKEN", "")

    # ------------------------------------------------------------------
    # Webhook
    # ------------------------------------------------------------------
    WEBHOOK_SECRET: str = os.environ.get("WEBHOOK_SECRET", "")

    # ------------------------------------------------------------------
    # Blockchain APIs
    # ------------------------------------------------------------------
    TRONGRID_API_KEY: str = os.environ.get("TRONGRID_API_KEY", "")
    BSCSCAN_API_KEY: str = os.environ.get("BSCSCAN_API_KEY", "")

    # USDT contract addresses
    USDT_TRC20_CONTRACT: str = os.environ.get(
        "USDT_TRC20_CONTRACT", "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    )
    USDT_BEP20_CONTRACT: str = os.environ.get(
        "USDT_BEP20_CONTRACT", "0x55d398326f99059fF775485246999027B3197955"
    )

    # ------------------------------------------------------------------
    # Invoice settings
    # ------------------------------------------------------------------
    # How many minutes before an unpaid invoice expires
    INVOICE_EXPIRY_MINUTES: int = int(os.environ.get("INVOICE_EXPIRY_MINUTES", "30"))

    # Minimum block confirmations before marking as "paid"
    TRC20_CONFIRMATIONS: int = int(os.environ.get("TRC20_CONFIRMATIONS", "20"))
    BEP20_CONFIRMATIONS: int = int(os.environ.get("BEP20_CONFIRMATIONS", "12"))

    # ------------------------------------------------------------------
    # Monitor polling interval (seconds)
    # ------------------------------------------------------------------
    POLL_INTERVAL: int = int(os.environ.get("POLL_INTERVAL", "20"))
