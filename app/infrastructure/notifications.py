"""Recordatorios multi-tenant idempotentes."""
import json
import os
from datetime import timedelta

from sqlalchemy.exc import IntegrityError
from twilio.rest import Client

from app.core.database import SessionLocal
from app.core.models import Agendamiento, NotificacionAgendamiento, get_now_chile
from app.infrastructure.email_utils import enviar_email_base


def _config(cita):
    try:
        return json.loads(cita.tenant.config_json or "{}")
    except (AttributeError, json.JSONDecodeError):
        return {}


def _registrar(db, cita, tipo, canal):
    db.add(NotificacionAgendamiento(tenant_id=cita.tenant_id, agendamiento_id=cita.id, tipo=tipo, canal=canal))
    try:
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        return False


def _ya_enviada(db, cita, tipo, canal):
    return db.query(NotificacionAgendamiento.id).filter(
        NotificacionAgendamiento.agendamiento_id == cita.id,
        NotificacionAgendamiento.tipo == tipo,
        NotificacionAgendamiento.canal == canal,
    ).first() is not None


def _mensaje(cita, tipo, empresa):
    fecha = cita.fecha_inicio.strftime("%d/%m/%Y a las %H:%M")
    if tipo == "creada":
        return f"Hola {cita.nombre}, tu agenda fue creada para el {fecha}. {empresa} te contactará si hay novedades."
    cuando = "mañana" if tipo == "recordatorio_24h" else "en una hora"
    return f"Hola {cita.nombre}, te recordamos que tu cita es {cuando}: {fecha}. Te esperamos en {empresa}."


def enviar_notificacion(cita_id, tipo):
    db = SessionLocal()
    try:
        cita = db.query(Agendamiento).filter(Agendamiento.id == cita_id).first()
        if not cita or cita.estado == "cancelado":
            return {"email": False, "whatsapp": False}
        cfg = _config(cita)
        canales = cfg.get("notificaciones", {})
        empresa = cfg.get("nombre_publico", cita.tenant.nombre_empresa)
        mensaje = _mensaje(cita, tipo, empresa)
        resultado = {"email": False, "whatsapp": False}
        if (canales.get("email", True) and not _ya_enviada(db, cita, tipo, "email")
                and enviar_email_base(cita.correo, f"Agenda · {empresa}", f"<p>{mensaje}</p>")):
            resultado["email"] = _registrar(db, cita, tipo, "email")
        sid, token, origen = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN"), os.getenv("TWILIO_WHATSAPP_NUMBER")
        if canales.get("whatsapp", True) and sid and token and origen and not _ya_enviada(db, cita, tipo, "whatsapp"):
            telefono = cita.telefono.strip()
            telefono = telefono if telefono.startswith("+") else f"+56{telefono.lstrip('0')}"
            try:
                Client(sid, token).messages.create(body=mensaje, from_=origen, to=f"whatsapp:{telefono}")
                resultado["whatsapp"] = _registrar(db, cita, tipo, "whatsapp")
            except Exception:
                pass
        return resultado
    finally:
        db.close()


def procesar_recordatorios(ahora=None):
    """Invocar cada 5 minutos desde un scheduler externo a Vercel Hobby."""
    ahora = ahora or get_now_chile()
    db = SessionLocal()
    try:
        citas = db.query(Agendamiento.id, Agendamiento.fecha_inicio).filter(
            Agendamiento.estado != "cancelado", Agendamiento.fecha_inicio > ahora
        ).all()
    finally:
        db.close()
    enviados = 0
    for cita_id, fecha_inicio in citas:
        for tipo, anticipacion in (("recordatorio_24h", timedelta(hours=24)), ("recordatorio_1h", timedelta(hours=1))):
            if ahora >= fecha_inicio - anticipacion:
                enviados += sum(enviar_notificacion(cita_id, tipo).values())
    return enviados
