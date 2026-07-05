from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.core import models, stripe_utils
from app.api import deps
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
            tenant.stripe_customer_id = customer_id
            tenant.stripe_subscription_id = subscription_id
            tenant.estado_suscripcion = "activa"
            # Determinar plan basado en el amount_total o metadata en un entorno real
            # tenant.plan_actual = "Pro" 
            db.commit()
            
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        tenant = db.query(models.Tenant).filter(models.Tenant.stripe_subscription_id == subscription.id).first()
        if tenant:
            tenant.estado_suscripcion = "cancelada"
            db.commit()
            
    return {"status": "success"}
