"""
webhook_server.py — Recibe notificaciones de Stan.store cuando alguien compra.
"""
import os
import hmac
import hashlib
import json
from flask import Flask, request, jsonify
import db

app = Flask(__name__)
STAN_WEBHOOK_SECRET = os.environ.get("STAN_WEBHOOK_SECRET", "")


def verificar_firma(payload: bytes, firma: str) -> bool:
    if not STAN_WEBHOOK_SECRET:
        return True
    esperada = hmac.new(STAN_WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma or "")


@app.route("/webhook/stan", methods=["POST"])
def stan_webhook():
    payload = request.get_data()
    firma   = request.headers.get("X-Stan-Signature", "")
    if not verificar_firma(payload, firma):
        return jsonify({"error": "firma inválida"}), 401
    try:
        data  = request.get_json()
        email = (
            data.get("email") or
            data.get("customer", {}).get("email") or
            data.get("buyer_email", "")
        ).lower().strip()
        if not email:
            return jsonify({"error": "sin email"}), 400
        db.set_pending_email(email)
        print(f"✅ Compra registrada: {email}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", **db.get_stats()})
