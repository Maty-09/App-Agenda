from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core import models, stripe_utils, mercadopago_utils
from app.api import deps
from app.infrastructure.email_utils import enviar_aviso_nueva_suscripcion, enviar_suscripcion_activada
import stripe
import os
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/checkout")
def create_checkout(
    plan: str,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_admin_empresa)
):
    """Genera un link de pago en Stripe para la empresa actual."""
    if plan not in ["Starter", "Pro", "Business"]:
        raise HTTPException(status_code=400, detail="Plan inválido")
        
    base_url = os.getenv("SYSTEM_BASE_URL", "https://agenda.norem.cl").rstrip("/")
    success_url = f"{base_url}/admin/suscripcion"
    cancel_url = f"{base_url}/admin/suscripcion?estado=cancelado"
    
    try:
        checkout_url = stripe_utils.create_checkout_session(
            tenant_id=current_user.tenant_id,
            plan=plan,
            success_url=success_url,
            cancel_url=cancel_url
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Pagos con tarjeta no están configurados.") from exc
    
    if not checkout_url:
        raise HTTPException(status_code=500, detail="No se pudo contactar a Stripe")
        
    return {"checkout_url": checkout_url}

@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(deps.get_db)):
    """Recibe notificaciones de Stripe (Pagos exitosos, cancelaciones)."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        raise HTTPException(status_code=400, detail="Missing signature")
        
    try:
        event = stripe_utils.verify_webhook_signature(payload, sig_header)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Webhook de Stripe no configurado.") from exc
    except (ValueError, stripe.error.SignatureVerificationError) as exc:
        raise HTTPException(status_code=400, detail="Firma o contenido del webhook inválido.") from exc
        
    _procesar_evento_stripe(event, db)
    return {"status": "success"}


ESTADOS_STRIPE_IMPAGOS = {"past_due", "unpaid", "incomplete_expired", "canceled"}


def _notificar_activacion(db: Session, tenant: models.Tenant, origen: str) -> None:
    """Correos de bienvenida. Un fallo de correo no debe revertir el pago."""
    try:
        usuario = db.query(models.Usuario).filter(models.Usuario.tenant_id == tenant.id, models.Usuario.rol == "admin").first()
        if usuario:
            enviar_suscripcion_activada(usuario.email, usuario.nombre)
            enviar_aviso_nueva_suscripcion(tenant, usuario, origen)
        tenant.suscripcion_notificada_at = models.get_now_chile()
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("subscription_activation_email_failed tenant_id=%s", tenant.id)


def _tenant_por_suscripcion_stripe(db: Session, subscription_id) -> models.Tenant | None:
    if not subscription_id:
        return None
    return db.query(models.Tenant).filter(models.Tenant.stripe_subscription_id == subscription_id).first()


def _procesar_evento_stripe(event, db: Session) -> None:
    tipo = event["type"]
    objeto = event["data"]["object"]

    if tipo == "checkout.session.completed":
        tenant = db.query(models.Tenant).filter(models.Tenant.id == objeto.get("client_reference_id")).first()
        if not tenant:
            return
        primera_activacion = tenant.estado_suscripcion != "activa"
        tenant.stripe_customer_id = objeto.get("customer")
        tenant.stripe_subscription_id = objeto.get("subscription")
        tenant.estado_suscripcion = "activa"
        tenant.plan_actual = (objeto.get("metadata") or {}).get("plan", "Norem Mensual")
        db.commit()
        if primera_activacion:
            _notificar_activacion(db, tenant, "Stripe")

    elif tipo in {"customer.subscription.updated", "customer.subscription.deleted"}:
        # Sólo cuenta la suscripción vigente del negocio; las antiguas se ignoran.
        tenant = _tenant_por_suscripcion_stripe(db, objeto.get("id"))
        if not tenant or tenant.estado_suscripcion == "cancelada":
            return
        estado = "canceled" if tipo == "customer.subscription.deleted" else objeto.get("status")
        if estado in ESTADOS_STRIPE_IMPAGOS:
            tenant.estado_suscripcion = "impaga"
        elif estado in {"active", "trialing"}:
            tenant.estado_suscripcion = "activa"
        db.commit()

    elif tipo in {"invoice.payment_failed", "invoice.paid"}:
        tenant = _tenant_por_suscripcion_stripe(db, objeto.get("subscription"))
        if not tenant or tenant.estado_suscripcion == "cancelada":
            return
        if tipo == "invoice.payment_failed":
            tenant.estado_suscripcion = "impaga"
        elif tenant.estado_suscripcion == "impaga":
            tenant.estado_suscripcion = "activa"
        db.commit()


@router.post("/mercadopago/webhook")
async def mercadopago_webhook(request: Request, db: Session = Depends(deps.get_db)):
    """Sincroniza las altas y bajas que Mercado Pago confirma mediante webhook."""
    try:
        payload = await request.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    data = payload.get("data") or {}
    # Mercado Pago firma el identificador enviado como query param `data.id`.
    # Conservamos el fallback al cuerpo para simulaciones y reintentos compatibles.
    preapproval_id = str(request.query_params.get("data.id") or data.get("id") or request.query_params.get("id") or "")
    if not mercadopago_utils.firma_webhook_valida(
        signature=request.headers.get("x-signature"),
        request_id=request.headers.get("x-request-id"),
        data_id=preapproval_id,
    ):
        raise HTTPException(status_code=401, detail="Firma de Mercado Pago inválida")

    event_type = payload.get("type") or payload.get("topic") or request.query_params.get("type") or request.query_params.get("topic")
    if event_type not in {"subscription_preapproval", "preapproval"}:
        return {"status": "ignored"}

    try:
        subscription = mercadopago_utils.obtener_suscripcion(preapproval_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    tenant_id = subscription.get("external_reference")
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        return {"status": "unknown_tenant"}
    if tenant.estado_suscripcion == "cancelada":
        # Cuenta desactivada manualmente por Norem: los pagos no la reactivan solos.
        return {"status": "ignored", "motivo": "cuenta_desactivada"}

    subscription_status = subscription.get("status")
    es_vigente = tenant.mercado_pago_preapproval_id == preapproval_id

    if subscription_status == "authorized":
        primera_activacion = tenant.estado_suscripcion != "activa"
        tenant.mercado_pago_preapproval_id = preapproval_id
        tenant.plan_actual = "Norem Mensual"
        tenant.estado_suscripcion = "activa"
        db.commit()
        if primera_activacion:
            _notificar_activacion(db, tenant, "Mercado Pago")
        return {"status": "success"}

    if subscription_status in {"cancelled", "paused", "expired"}:
        # Un intento de pago viejo o abandonado no puede afectar a la
        # suscripción que el negocio tiene vigente.
        if not es_vigente:
            return {"status": "ignored", "motivo": "suscripcion_no_vigente"}
        tenant.estado_suscripcion = "impaga"
        db.commit()
        return {"status": "success"}

    # Una preaprobación pendiente es normal mientras el cliente termina el
    # checkout. No debe cancelar una prueba ni una suscripción ya activa.
    return {"status": "pending", "mercado_pago_status": subscription_status}
