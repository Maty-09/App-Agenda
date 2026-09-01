"""API pública para integrar la agenda de cada negocio en su propio sitio web."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core import models
from app.core.database import get_db
from app.domain_agenda.router_cliente import obtener_horas_disponibles

router = APIRouter()


def _tenant_y_config(db: Session, tenant_id: str):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    try:
        config = json.loads(tenant.config_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        config = {}
    return tenant, config


@router.get("/{tenant_id}/agenda")
def agenda_publica(tenant_id: str, db: Session = Depends(get_db)):
    """Entrega la configuración pública y URL de reserva para un sitio externo."""
    tenant, config = _tenant_y_config(db, tenant_id)
    negocio = config.get("negocio", {})
    return {
        "negocio": {"id": tenant.id, "nombre": tenant.nombre_empresa, "actividad": negocio.get("giro", ""), "servicio_principal": negocio.get("servicio_principal", ""), "duracion_minutos": negocio.get("duracion_minutos", 60)},
        "reglas": config.get("reglas_negocio", {}),
        "booking_url": f"/cliente/{tenant.id}/agendar_web",
        "embed_script": f"/api/v1/public/{tenant.id}/agenda/widget.js",
    }


@router.get("/{tenant_id}/agenda/disponibilidad")
def disponibilidad_publica(tenant_id: str, fecha: str = Query(..., pattern=r"^\d{4}-\d{2}-\d{2}$"), db: Session = Depends(get_db)):
    """Devuelve horarios disponibles; útil si el cliente construye su propia interfaz."""
    tenant, config = _tenant_y_config(db, tenant_id)
    try:
        dia = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Fecha inválida") from exc
    minutos = config.get("negocio", {}).get("duracion_minutos", 60)
    horas = obtener_horas_disponibles("domicilio_taller", dia, max(1, round(minutos / 60)), db, tenant.id)
    return {"fecha": fecha, "horas": horas}


@router.get("/{tenant_id}/agenda/widget.js")
def widget_agenda(tenant_id: str, db: Session = Depends(get_db)):
    """Widget sin dependencias: basta incluir este script donde se quiere mostrar la agenda."""
    _tenant_y_config(db, tenant_id)
    script = f'''(function(){{
  var script=document.currentScript, base=new URL(script.src).origin;
  var frame=document.createElement('iframe');
  frame.src=base+'/cliente/{tenant_id}/agendar_web'; frame.title='Agenda online';
  frame.style.cssText='width:100%;min-height:780px;border:0;border-radius:16px;';
  script.parentNode.insertBefore(frame,script.nextSibling);
}})();'''
    return Response(script, media_type="application/javascript", headers={"Access-Control-Allow-Origin": "*"})
