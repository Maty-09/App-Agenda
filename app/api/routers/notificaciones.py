import os
import secrets

from fastapi import APIRouter, Header, HTTPException

from app.infrastructure.notifications import procesar_recordatorios

router = APIRouter()


@router.get("/cron/notificaciones")
def ejecutar_recordatorios(authorization: str | None = Header(default=None)):
    secreto = os.getenv("CRON_SECRET")
    if not secreto or not authorization or not secrets.compare_digest(authorization, f"Bearer {secreto}"):
        raise HTTPException(status_code=401, detail="No autorizado")
    return {"notificaciones_enviadas": procesar_recordatorios()}
