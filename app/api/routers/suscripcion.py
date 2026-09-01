from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core import models, stripe_utils, mercadopago_utils
from app.api import deps
from app.infrastructure.email_utils import enviar_aviso_nueva_suscripcion, enviar_suscripcion_activada
import stripe

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
        
    success_url = "http://localhost:5173/dashboard?pago=exito"
    cancel_url = "http://localhost:5173/dashboard?pago=cancelado"
    
    checkout_url = stripe_utils.create_checkout_session(
        tenant_id=current_user.tenant_id,
        plan=plan,
        success_url=success_url,
        cancel_url=cancel_url
    )
    
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
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    # Manejar el evento
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        tenant_id = session.get('client_reference_id')
        customer_id = session.get('customer')
        subscription_id = session.get('subscription')
        
        # Actualizar base de datos
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
        if tenant:
            primera_activacion = tenant.estado_suscripcion != "activa"
            tenant.stripe_customer_id = customer_id
            tenant.stripe_subscription_id = subscription_id
            tenant.estado_suscripcion = "activa"
            tenant.plan_actual = session.get("metadata", {}).get("plan", "Norem Mensual")
            db.commit()
            if primera_activacion:
                usuario = db.query(models.Usuario).filter(models.Usuario.tenant_id == tenant.id, models.Usuario.rol == "admin").first()
                if usuario:
                    enviar_suscripcion_activada(usuario.email, usuario.nombre)
                    enviar_aviso_nueva_suscripcion(tenant, usuario, "Stripe")
                tenant.suscripcion_notificada_at = models.get_now_chile()
                db.commit()
            
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        tenant = db.query(models.Tenant).filter(models.Tenant.stripe_subscription_id == subscription.id).first()
        if tenant:
            tenant.estado_suscripcion = "cancelada"
            db.commit()
            
    return {"status": "success"}


@router.post("/mercadopago/webhook")
async def mercadopago_webhook(request: Request, db: Session = Depends(deps.get_db)):
    """Sincroniza las altas y bajas que Mercado Pago confirma mediante webhook."""
    payload = await request.json()
    data = payload.get("data") or {}
    preapproval_id = str(data.get("id") or "")
    if not mercadopago_utils.firma_webhook_valida(
        signature=request.headers.get("x-signature"),
        request_id=request.headers.get("x-request-id"),
        data_id=preapproval_id,
    ):
        raise HTTPException(status_code=401, detail="Firma de Mercado Pago inválida")

    event_type = payload.get("type") or payload.get("topic")
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

    primera_activacion = tenant.estado_suscripcion != "activa" and subscription.get("status") == "authorized"
    tenant.mercado_pago_preapproval_id = preapproval_id
    tenant.plan_actual = "Norem Mensual"
    tenant.estado_suscripcion = "activa" if subscription.get("status") == "authorized" else "cancelada"
    db.commit()
    if primera_activacion:
        usuario = db.query(models.Usuario).filter(models.Usuario.tenant_id == tenant.id, models.Usuario.rol == "admin").first()
        if usuario:
            enviar_suscripcion_activada(usuario.email, usuario.nombre)
            enviar_aviso_nueva_suscripcion(tenant, usuario, "Mercado Pago")
        tenant.suscripcion_notificada_at = models.get_now_chile()
        db.commit()
    return {"status": "success"}
