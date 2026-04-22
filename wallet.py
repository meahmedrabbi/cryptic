"""
wallet.py – Deterministic unique wallet generation for TRC-20 and BEP-20.

Each invoice gets its own deposit address so payments can be matched 1-to-1.
Private keys are returned to the caller and must be encrypted before storage.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WalletInfo:
    address: str
    private_key: str  # plaintext – encrypt immediately after use!


# ---------------------------------------------------------------------------
# BEP-20 (BSC / EVM-compatible)
# ---------------------------------------------------------------------------

def generate_bep20_wallet() -> WalletInfo:
    """Generate a fresh BEP-20 (BSC) wallet using eth-account."""
    from eth_account import Account

    acct = Account.create()
    return WalletInfo(address=acct.address, private_key=acct.key.hex())


# ---------------------------------------------------------------------------
# TRC-20 (TRON)
# ---------------------------------------------------------------------------

def generate_trc20_wallet() -> WalletInfo:
    """Generate a fresh TRC-20 (TRON) wallet using tronpy."""
    from tronpy.keys import PrivateKey

    priv = PrivateKey.random()
    address = priv.public_key.to_base58check_address()
    return WalletInfo(address=address, private_key=priv.hex())


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------

def generate_wallet(network: str) -> WalletInfo:
    """Return a new wallet for *network* ('trc20' or 'bep20')."""
    if network == "trc20":
        return generate_trc20_wallet()
    if network == "bep20":
        return generate_bep20_wallet()
    raise ValueError(f"Unsupported network: {network!r}. Use 'trc20' or 'bep20'.")
