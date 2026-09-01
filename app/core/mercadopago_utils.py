"""Integración server-side de suscripciones de Mercado Pago."""

import hashlib
import hmac
import os
from typing import Any, Dict, Optional

import requests


API_URL = "https://api.mercadopago.com"


def _access_token() -> str:
    token = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    if not token:
        raise RuntimeError("Falta configurar Mercado Pago para crear la suscripción.")
    return token


def crear_suscripcion_mensual(tenant_id: str, payer_email: str, back_url: str) -> str:
    """Crea una preaprobación individual y retorna su checkout seguro."""
    response = requests.post(
        f"{API_URL}/preapproval",
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
        json={
            "reason": "Norem Mensual",
            "external_reference": tenant_id,
            "payer_email": payer_email,
            "back_url": back_url,
            "auto_recurring": {
                "frequency": 1,
                "frequency_type": "months",
                "transaction_amount": 14990,
                "currency_id": "CLP",
            },
            "status": "pending",
        },
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError("Mercado Pago no pudo iniciar la suscripción.")
    data = response.json()
    checkout_url = data.get("init_point")
    if not checkout_url:
        raise RuntimeError("Mercado Pago no devolvió un enlace de pago.")
    return checkout_url, data.get("id")


def obtener_suscripcion(preapproval_id: str) -> Dict[str, Any]:
    response = requests.get(
        f"{API_URL}/preapproval/{preapproval_id}",
        headers={"Authorization": f"Bearer {_access_token()}"},
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError("No se pudo verificar la suscripción en Mercado Pago.")
    return response.json()


def cancelar_suscripcion(preapproval_id: str) -> None:
    """Cancela el cobro recurrente antes de borrar una cuenta."""
    response = requests.put(
        f"{API_URL}/preapproval/{preapproval_id}",
        headers={"Authorization": f"Bearer {_access_token()}", "Content-Type": "application/json"},
        json={"status": "cancelled"},
        timeout=15,
    )
    if not response.ok:
        raise RuntimeError("Mercado Pago no pudo cancelar la suscripción.")


def firma_webhook_valida(
    *, signature: Optional[str], request_id: Optional[str], data_id: Optional[str]
) -> bool:
    """Valida la firma x-signature de Mercado Pago sin aceptar callbacks falsos."""
    secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()
    if not secret or not signature or not request_id or not data_id:
        return False
    parts = dict(
        item.split("=", 1) for item in signature.split(",") if "=" in item
    )
    timestamp, received_hash = parts.get("ts"), parts.get("v1")
    if not timestamp or not received_hash:
        return False
    manifest = f"id:{data_id};request-id:{request_id};ts:{timestamp};"
    calculated = hmac.new(secret.encode(), manifest.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculated, received_hash)
