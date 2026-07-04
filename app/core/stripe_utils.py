import stripe
import os
from dotenv import load_dotenv

load_dotenv()

stripe.api_key = ***REMOVED***
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mock_key")

# IDs de Precios (Deberían estar en Stripe Dashboard)
STRIPE_PRICE_STARTER = os.getenv("STRIPE_PRICE_STARTER", "price_starter_mock")
STRIPE_PRICE_PRO = os.getenv("STRIPE_PRICE_PRO", "price_pro_mock")
STRIPE_PRICE_BUSINESS = os.getenv("STRIPE_PRICE_BUSINESS", "price_business_mock")

def create_checkout_session(tenant_id: str, plan: str, success_url: str, cancel_url: str):
    """Crea una sesión de Checkout en Stripe para suscribirse a un plan."""
    
    price_id = STRIPE_PRICE_STARTER
    if plan == "Pro":
        price_id = STRIPE_PRICE_PRO
    elif plan == "Business":
        price_id = STRIPE_PRICE_BUSINESS
        
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
    except Exception as e:
        print(f"Error creando Stripe Checkout: {e}")
        return None

def verify_webhook_signature(payload: bytes, sig_header: str):
    """Verifica la firma del Webhook de Stripe."""
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
