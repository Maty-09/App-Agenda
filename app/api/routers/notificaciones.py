import os
import secrets

from fastapi import APIRouter, Header, HTTPException

from app.infrastructure.notifications import procesar_recordatorios
from app.infrastructure.email_utils import enviar_prueba_vencida
from app.core import models
from app.core.database import SessionLocal

router = APIRouter()


@router.get("/cron/notificaciones")
def ejecutar_recordatorios(authorization: str | None = Header(default=None)):
    secreto = os.getenv("CRON_SECRET")
    if not secreto or not authorization or not secrets.compare_digest(authorization, f"Bearer {secreto}"):
        raise HTTPException(status_code=401, detail="No autorizado")
    return {"notificaciones_enviadas": procesar_recordatorios()}


@router.get("/cron/pruebas-vencidas")
def ejecutar_pruebas_vencidas(authorization: str | None = Header(default=None)):
    secreto = os.getenv("CRON_SECRET")
    if not secreto or not authorization or not secrets.compare_digest(authorization, f"Bearer {secreto}"):
        raise HTTPException(status_code=401, detail="No autorizado")
    db = SessionLocal()
    enviados = 0
    try:
        tenants = db.query(models.Tenant).filter(models.Tenant.estado_suscripcion == "prueba", models.Tenant.trial_fin <= models.get_now_chile(), models.Tenant.trial_vencimiento_notificado_at == None).all()
        for tenant in tenants:
            usuario = db.query(models.Usuario).filter(models.Usuario.tenant_id == tenant.id, models.Usuario.rol == "admin").first()
            if usuario and enviar_prueba_vencida(usuario.email, usuario.nombre):
                tenant.trial_vencimiento_notificado_at = models.get_now_chile()
                enviados += 1
        db.commit()
    finally:
        db.close()
    return {"pruebas_notificadas": enviados}
