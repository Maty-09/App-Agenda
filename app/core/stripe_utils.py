import stripe
import os
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# IDs de precios configurados en el panel de Stripe; no usar IDs ficticios.
STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO")
STRIPE_PRICE_BUSINESS = os.getenv("STRIPE_PRICE_BUSINESS")
STRIPE_PRICE_NOREM_MENSUAL = os.getenv("STRIPE_PRICE_NOREM_MENSUAL")

def create_checkout_session(tenant_id: str, plan: str, success_url: str, cancel_url: str):
    """Crea una sesión de Checkout en Stripe para suscribirse a un plan."""
    
    price_id = STRIPE_PRICE_STARTER
    if plan == "Pro":
        price_id = STRIPE_PRICE_PRO
    elif plan == "Business":
        price_id = STRIPE_PRICE_BUSINESS

    if not stripe.api_key or not price_id:
        raise RuntimeError(f"Stripe no está configurado para el plan {plan}.")
        
    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=cancel_url,
            client_reference_id=tenant_id,
        )
        return session.url
    except Exception:
        logger.error("stripe_checkout_creation_failed")
        return None


def create_norem_monthly_checkout_session(tenant_id: str, success_url: str, cancel_url: str):
    """Checkout del plan Norem completo: $14.990 CLP mensuales."""
    if not stripe.api_key or not STRIPE_PRICE_NOREM_MENSUAL:
        raise RuntimeError("La suscripción aún no está configurada para recibir pagos.")
    return stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": STRIPE_PRICE_NOREM_MENSUAL, "quantity": 1}],
        success_url=f"{success_url}?estado=exito&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{cancel_url}?estado=cancelado",
        client_reference_id=tenant_id,
        metadata={"tenant_id": tenant_id, "plan": "Norem Mensual"},
    ).url


def verify_webhook_signature(payload: bytes, sig_header: str):
    """Verifica la firma del Webhook de Stripe."""
    if not STRIPE_WEBHOOK_SECRET:
        raise RuntimeError("STRIPE_WEBHOOK_SECRET no está configurado.")
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
        return event
    except ValueError as e:
        # Payload inválido
        raise e
    except stripe.error.SignatureVerificationError as e:
        # Firma inválida
        raise e
