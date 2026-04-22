"""
app.py – Flask application entry point with API routes and admin dashboard.
"""

from __future__ import annotations

import base64
import io
import logging
import os
from datetime import datetime, timedelta, timezone
from functools import wraps

import qrcode
from apscheduler.schedulers.background import BackgroundScheduler
from flask import Flask, abort, jsonify, render_template, request

from config import Config
from models import Network, Payment, PaymentStatus, db
from security import encrypt_key
from wallet import generate_wallet

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s – %(message)s",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(config_object: object = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    # Database
    db.init_app(app)
    with app.app_context():
        db.create_all()

    # Background scheduler
    scheduler = BackgroundScheduler(timezone="UTC")
    poll_interval = int(app.config.get("POLL_INTERVAL", 20))

    def _poll():
        from monitor import poll_payments
        poll_payments(app)

    scheduler.add_job(_poll, "interval", seconds=poll_interval, id="payment_monitor")
    scheduler.start()

    # ---------------------------------------------------------------------------
    # Auth helper
    # ---------------------------------------------------------------------------

    def require_admin(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = app.config.get("ADMIN_TOKEN", "")
            auth_header = request.headers.get("Authorization", "")
            if not token or auth_header != f"Bearer {token}":
                abort(401)
            return f(*args, **kwargs)
        return decorated

    # ---------------------------------------------------------------------------
    # API – Create payment invoice
    # ---------------------------------------------------------------------------

    @app.route("/api/payment/create", methods=["POST"])
    def create_payment():
        data = request.get_json(force=True, silent=True) or {}

        order_id = data.get("order_id", "").strip()
        amount = data.get("amount")
        network_str = data.get("network", "").lower().strip()
        webhook_url = data.get("webhook_url", "").strip() or None

        # --- Validation ---
        if not order_id:
            return jsonify({"error": "order_id is required"}), 400
        if amount is None:
            return jsonify({"error": "amount is required"}), 400
        try:
            amount = float(amount)
            if amount <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return jsonify({"error": "amount must be a positive number"}), 400
        if network_str not in ("trc20", "bep20"):
            return jsonify({"error": "network must be 'trc20' or 'bep20'"}), 400
        if Payment.query.filter_by(order_id=order_id).first():
            return jsonify({"error": f"order_id '{order_id}' already exists"}), 409

        # --- Generate wallet ---
        wallet = generate_wallet(network_str)
        encrypted_pk = encrypt_key(wallet.private_key)

        # --- Persist ---
        expiry_minutes = int(app.config.get("INVOICE_EXPIRY_MINUTES", 30))
        now = datetime.now(timezone.utc)
        payment = Payment(
            order_id=order_id,
            network=Network(network_str),
            address=wallet.address,
            private_key_enc=encrypted_pk,
            amount_expected=amount,
            amount_received=0,
            status=PaymentStatus.pending,
            webhook_url=webhook_url,
            created_at=now,
            expires_at=now + timedelta(minutes=expiry_minutes),
        )
        db.session.add(payment)
        db.session.commit()

        logger.info("Invoice created: order=%s network=%s address=%s", order_id, network_str, wallet.address)

        return (
            jsonify(
                {
                    "order_id": payment.order_id,
                    "address": payment.address,
                    "amount": float(payment.amount_expected),
                    "network": payment.network.value,
                    "status": payment.status.value,
                    "expires_at": payment.expires_at.isoformat(),
                }
            ),
            201,
        )

    # ---------------------------------------------------------------------------
    # API – Get payment status
    # ---------------------------------------------------------------------------

    @app.route("/api/payment/<order_id>", methods=["GET"])
    def get_payment(order_id: str):
        payment = Payment.query.filter_by(order_id=order_id).first_or_404()
        return jsonify(payment.to_dict())

    # ---------------------------------------------------------------------------
    # API – QR code for payment address
    # ---------------------------------------------------------------------------

    @app.route("/api/payment/<order_id>/qr", methods=["GET"])
    def get_qr(order_id: str):
        payment = Payment.query.filter_by(order_id=order_id).first_or_404()

        # Build a simple URI; wallets understand plain addresses too
        uri = payment.address

        img = qrcode.make(uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        encoded = base64.b64encode(buf.read()).decode()
        return jsonify(
            {
                "order_id": payment.order_id,
                "address": payment.address,
                "network": payment.network.value,
                "qr_base64": f"data:image/png;base64,{encoded}",
            }
        )

    # ---------------------------------------------------------------------------
    # API – List all payments (admin)
    # ---------------------------------------------------------------------------

    @app.route("/api/payments", methods=["GET"])
    @require_admin
    def list_payments():
        page = request.args.get("page", 1, type=int)
        per_page = min(request.args.get("per_page", 50, type=int), 100)
        status_filter = request.args.get("status")
        network_filter = request.args.get("network")

        query = Payment.query.order_by(Payment.created_at.desc())
        if status_filter:
            try:
                query = query.filter(Payment.status == PaymentStatus(status_filter))
            except ValueError:
                return jsonify({"error": f"Invalid status: {status_filter}"}), 400
        if network_filter:
            try:
                query = query.filter(Payment.network == Network(network_filter))
            except ValueError:
                return jsonify({"error": f"Invalid network: {network_filter}"}), 400

        paginated = query.paginate(page=page, per_page=per_page, error_out=False)
        return jsonify(
            {
                "payments": [p.to_dict() for p in paginated.items],
                "total": paginated.total,
                "page": paginated.page,
                "pages": paginated.pages,
            }
        )

    # ---------------------------------------------------------------------------
    # Admin dashboard
    # ---------------------------------------------------------------------------

    @app.route("/dashboard", methods=["GET"])
    @require_admin
    def dashboard():
        payments = Payment.query.order_by(Payment.created_at.desc()).limit(200).all()
        return render_template("dashboard.html", payments=payments)

    return app


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    application = create_app()
    application.run(host="0.0.0.0", port=int(os.environ.get("PORT", "5000")))
