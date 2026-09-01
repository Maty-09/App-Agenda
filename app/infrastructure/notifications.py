"""Recordatorios multi-tenant idempotentes."""
import json
import os
from datetime import timedelta
from html import escape

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


def _correo_html(cita, tipo, empresa, mensaje):
    """Construye el correo inicial y los recordatorios con HTML compatible con clientes de email."""
    nombre = escape(str(cita.nombre or ""))
    empresa = escape(str(empresa or "Norem"))
    fecha = escape(cita.fecha_inicio.strftime("%d/%m/%Y"))
    hora = escape(cita.fecha_inicio.strftime("%H:%M"))
    servicio = escape(str(getattr(cita, "tipo_servicio", "Servicio") or "Servicio").replace("_", " ").title())
    texto = escape(mensaje)
    if tipo == "creada":
        etiqueta, titulo, color = "SOLICITUD RECIBIDA", "Tu cita fue agendada", "#2563eb"
    else:
        etiqueta, titulo, color = "RECORDATORIO", "Tu cita se acerca", "#7c3aed"

    return f"""<!doctype html>
<html lang=\"es\"><body style=\"margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;\">
  <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"padding:32px 16px;background:#f1f5f9;\"><tr><td align=\"center\">
    <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"max-width:600px;background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e2e8f0;\">
      <tr><td style=\"padding:28px 36px;background:{color};\"><p style=\"margin:0 0 8px;color:#dbeafe;font-size:11px;font-weight:bold;letter-spacing:1.4px;\">{etiqueta}</p><h1 style=\"margin:0;color:#ffffff;font-size:24px;line-height:1.2;\">{titulo}</h1></td></tr>
      <tr><td style=\"padding:32px 36px;\"><p style=\"margin:0 0 18px;font-size:16px;line-height:1.6;\">Hola {nombre},</p><p style=\"margin:0 0 24px;color:#475569;font-size:16px;line-height:1.6;\">{texto}</p>
        <table role=\"presentation\" width=\"100%\" cellspacing=\"0\" cellpadding=\"0\" style=\"border:1px solid #e2e8f0;border-radius:10px;background:#f8fafc;\">
          <tr><td style=\"padding:14px 18px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;\">Fecha</td><td align=\"right\" style=\"padding:14px 18px;border-bottom:1px solid #e2e8f0;font-size:14px;font-weight:bold;\">{fecha}</td></tr>
          <tr><td style=\"padding:14px 18px;border-bottom:1px solid #e2e8f0;color:#64748b;font-size:13px;\">Hora</td><td align=\"right\" style=\"padding:14px 18px;border-bottom:1px solid #e2e8f0;font-size:14px;font-weight:bold;\">{hora} hrs</td></tr>
          <tr><td style=\"padding:14px 18px;color:#64748b;font-size:13px;\">Servicio</td><td align=\"right\" style=\"padding:14px 18px;font-size:14px;font-weight:bold;\">{servicio}</td></tr>
        </table>
      </td></tr>
      <tr><td style=\"padding:20px 36px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.5;text-align:center;\">Mensaje automático de {empresa}. Si necesitas ayuda, contacta directamente al negocio.</td></tr>
    </table>
  </td></tr></table>
</body></html>"""


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
                and enviar_email_base(
                    cita.correo,
                    f"Agenda · {empresa}",
                    _correo_html(cita, tipo, empresa, mensaje),
                    contenido_texto=mensaje,
                )):
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
