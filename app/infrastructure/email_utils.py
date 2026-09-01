import os
import smtplib
import vobject
import logging
import base64
from datetime import datetime, timedelta
from dotenv import load_dotenv
from email.utils import formataddr, formatdate, make_msgid, parseaddr
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import urllib.parse
import requests
import json
import re
import html
from app.core.database import SessionLocal 
from app.core.models import Agendamiento, get_now_chile

load_dotenv()

# --- CONFIGURACIÓN GLOBAL ---
REMITENTE = os.getenv("EMAIL_SENDER", "no-reply@norem.cl")
PASSWORD = os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_TOKEN")


def _reply_to_configurado(valor: str | None, remitente: str) -> str:
    """Evita que una variable de ejemplo termine en correos reales.

    Una respuesta siempre debe volver a un buzón del dominio que envía el
    mensaje si no se ha configurado un Reply-To real.
    """
    candidato = (valor or "").strip()
    _, direccion = parseaddr(candidato)
    if not direccion or "@" not in direccion or "tu-dominio" in direccion.lower():
        return remitente
    return candidato


REPLY_TO = _reply_to_configurado(os.getenv("EMAIL_REPLY_TO"), REMITENTE)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "").strip()
SMTP_HOST = os.getenv("SMTP_HOST", "server.dns-principal-34.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_TIMEOUT_SECONDS = float(os.getenv("SMTP_TIMEOUT_SECONDS", "15"))
CORREO_LOCAL = os.getenv("EMAIL_ADMIN", "matiasduranm09@gmail.com")
# URL pública para los enlaces de confirmación enviados a clientes.
BASE_URL = os.getenv("SYSTEM_BASE_URL", "https://agenda.norem.cl").rstrip("/")
logger = logging.getLogger(__name__)
logger.info(
    "email_configuration_loaded sender_configured=%s password_configured=%s smtp_configured=%s",
    bool(REMITENTE), bool(PASSWORD), bool(SMTP_HOST),
)


def plantilla_norem(asunto: str, contenido_html: str) -> str:
    """Envuelve cualquier correo heredado en una presentación Norem uniforme."""
    fuente = re.sub(r"<(script|style)[^>]*>.*?</\\1>", "", contenido_html or "", flags=re.IGNORECASE | re.DOTALL)
    enlaces = re.findall(r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', fuente, flags=re.IGNORECASE | re.DOTALL)
    texto = re.sub(r"<[^>]+>", " ", fuente)
    texto = re.sub(r"\\s+", " ", html.unescape(texto)).strip()
    parrafos = "".join(f'<p style="margin:0 0 14px;color:#475569;font-size:16px;line-height:1.6;">{html.escape(fragmento)}</p>' for fragmento in re.split(r"(?<=[.!?])\\s+", texto) if fragmento)
    acciones = "".join(
        f'<p style="margin:18px 0 0;text-align:center;"><a href="{html.escape(url, quote=True)}" style="display:inline-block;border-radius:9px;background:#0755bf;color:#fff;padding:12px 18px;font-weight:700;text-decoration:none;">{html.escape(re.sub(r"<[^>]+>", " ", html.unescape(etiqueta)).strip() or "Abrir enlace")}</a></p>'
        for url, etiqueta in enlaces[:3]
    )
    titulo = html.escape(asunto)
    return f'''<!doctype html><html lang="es"><body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:32px 16px;"><tr><td align="center"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;background:#fff;border:1px solid #e2e8f0;border-radius:16px;overflow:hidden;"><tr><td align="center" style="background:linear-gradient(135deg,#0b3d91,#0755bf);padding:26px;"><div style="display:inline-block;width:42px;height:42px;line-height:42px;border-radius:10px;background:#fff;color:#0755bf;font-size:24px;font-weight:800;">N</div><div style="margin-top:9px;color:#fff;font-size:18px;font-weight:800;letter-spacing:4px;">NOREM</div></td></tr><tr><td style="padding:32px 36px;"><h1 style="margin:0 0 18px;color:#0f172a;font-size:23px;line-height:1.3;">{titulo}</h1>{parrafos}{acciones}</td></tr><tr><td style="padding:18px 36px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.5;text-align:center;">Mensaje automático de Norem. No compartas contraseñas ni códigos de acceso.</td></tr></table></td></tr></table></body></html>'''

def _enviar_con_resend(destinatario, asunto, contenido_html, contenido_texto, adjunto_path, adjunto_name):
    """Envía por API transaccional, con mejor trazabilidad y reputación para Gmail."""
    payload = {
        "from": formataddr(("Norem", REMITENTE)),
        "to": [destinatario],
        "subject": asunto,
        "html": contenido_html,
        "text": contenido_texto,
        "reply_to": REPLY_TO,
    }
    if adjunto_path:
        contenido = adjunto_path if isinstance(adjunto_path, bytes) else str(adjunto_path).encode("utf-8")
        payload["attachments"] = [{
            "filename": adjunto_name or "adjunto",
            "content": base64.b64encode(contenido).decode("ascii"),
        }]
    try:
        response = requests.post(
            "https://api.resend.com/emails",
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "User-Agent": "Norem/1.0",
            },
            json=payload,
            timeout=15,
        )
        if response.ok:
            logger.info("resend_message_accepted")
            return True
        logger.error("resend_message_failed status=%s", response.status_code)
    except requests.RequestException:
        logger.exception("resend_request_failed")
    return False


def enviar_email_base(destinatario, asunto, contenido_html, adjunto_path=None, adjunto_name=None, contenido_texto=None):
    """Envía correo HTML con alternativa de texto plano y adjuntos opcionales."""
    contenido_html = plantilla_norem(asunto, contenido_html)
    msg = MIMEMultipart("mixed" if adjunto_path else "alternative")
    texto_plano = contenido_texto or "Tienes una actualización de tu agenda. Abre este correo en un cliente compatible con HTML."
    if RESEND_API_KEY:
        return _enviar_con_resend(destinatario, asunto, contenido_html, texto_plano, adjunto_path, adjunto_name)

    msg['From'] = formataddr(("Norem", REMITENTE))
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg['Reply-To'] = REPLY_TO
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain=REMITENTE.rsplit("@", 1)[-1])
    alternativa = MIMEMultipart("alternative") if adjunto_path else msg
    alternativa.attach(MIMEText(
        texto_plano,
        "plain",
        "utf-8",
    ))
    alternativa.attach(MIMEText(contenido_html, "html", "utf-8"))
    if adjunto_path:
        msg.attach(alternativa)

    if adjunto_path:
        part = MIMEBase('application', "octet-stream")
        part.set_payload(adjunto_path)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{adjunto_name}"')
        msg.attach(part)

    if not REMITENTE or not PASSWORD:
        missing = []
        if not REMITENTE: missing.append("EMAIL_SENDER")
        if not PASSWORD:  missing.append("EMAIL_PASSWORD / EMAIL_TOKEN")
        logger.error("email_configuration_missing variables=%s", ",".join(missing))
        return False

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            server.login(REMITENTE, PASSWORD)
            rechazados = server.sendmail(REMITENTE, [destinatario], msg.as_string())
        if rechazados:
            logger.warning("smtp_recipient_rejected rejected_count=%d", len(rechazados))
            return False
        logger.info("smtp_message_accepted host=%s port=%d", SMTP_HOST, SMTP_PORT)
        return True
    except (OSError, smtplib.SMTPException):
        logger.exception("smtp_message_failed")
        return False


def enviar_correo_recuperacion_contrasena(destinatario: str, nombre: str, url_restauracion: str) -> bool:
    """Envía un enlace de un solo uso para recuperar el acceso a Norem."""
    asunto = "Restablece tu contraseña de Norem"
    contenido_html = f"""
    <html><body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:40px 16px;"><tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 10px 28px rgba(15,23,42,.10);">
          <tr><td style="background:linear-gradient(135deg,#0b3d91,#0755bf);padding:28px 36px;text-align:center;">
            <div style="display:inline-block;width:46px;height:46px;line-height:46px;background:#fff;border-radius:12px;color:#0755bf;font-weight:800;font-size:28px;">N</div>
            <div style="margin-top:10px;color:#fff;font-weight:800;letter-spacing:5px;font-size:20px;">NOREM</div>
          </td></tr>
          <tr><td style="padding:36px;">
            <h1 style="font-size:24px;margin:0 0 16px;color:#0f172a;">Restablece tu contraseña</h1>
            <p style="font-size:16px;line-height:1.6;margin:0 0 20px;color:#475569;">Hola {nombre}, recibimos una solicitud para cambiar la contraseña de tu cuenta Norem.</p>
            <p style="font-size:16px;line-height:1.6;margin:0 0 28px;color:#475569;">Haz clic en el botón para elegir una nueva contraseña. El enlace vence en 30 minutos.</p>
            <p style="text-align:center;margin:0 0 28px;"><a href="{url_restauracion}" style="display:inline-block;background:#0755bf;color:#fff;text-decoration:none;font-weight:700;padding:14px 24px;border-radius:10px;">Restablecer contraseña</a></p>
            <p style="font-size:13px;line-height:1.5;margin:0;color:#64748b;">Si no solicitaste este cambio, puedes ignorar este correo. Tu contraseña actual seguirá siendo válida.</p>
          </td></tr>
          <tr><td style="background:#f8fafc;padding:18px 36px;text-align:center;color:#64748b;font-size:12px;">Este es un mensaje automático de Norem.</td></tr>
        </table>
      </td></tr></table>
    </body></html>
    """
    return enviar_email_base(destinatario, asunto, contenido_html)


def enviar_aviso_inicio_prueba(tenant, usuario) -> bool:
    """Avisa al equipo de Norem una vez creada una prueba válida."""
    inicio = tenant.trial_inicio.strftime("%d/%m/%Y %H:%M") if tenant.trial_inicio else "No disponible"
    fin = tenant.trial_fin.strftime("%d/%m/%Y") if tenant.trial_fin else "No disponible"
    html = (
        "<h2>Nueva prueba iniciada en Norem</h2>"
        f"<p><b>Negocio:</b> {tenant.nombre_empresa}</p>"
        f"<p><b>Administrador:</b> {usuario.nombre} · {usuario.email}</p>"
        f"<p><b>Inicio:</b> {inicio} (Chile)</p>"
        f"<p><b>Finaliza:</b> {fin}</p>"
    )
    return enviar_email_base(CORREO_LOCAL, "Nueva prueba iniciada en Norem", html)


def enviar_aviso_nueva_suscripcion(tenant, usuario, proveedor: str) -> bool:
    """Alerta interna al dueño de Norem, sin exponer datos sensibles en logs."""
    fecha = get_now_chile().strftime("%d/%m/%Y %H:%M")
    html = f"<h2>Nueva suscripción Norem</h2><p><b>Negocio:</b> {tenant.nombre_empresa}</p><p><b>Cliente:</b> {usuario.nombre} · {usuario.email}</p><p><b>Origen:</b> {proveedor}</p><p><b>Fecha:</b> {fecha} (Chile)</p>"
    return enviar_email_base(CORREO_LOCAL, "Nueva suscripción en Norem", html)


def enviar_suscripcion_activada(destinatario: str, nombre: str) -> bool:
    return enviar_email_base(destinatario, "Tu suscripción Norem está activa", f"<h2>¡Todo listo, {nombre}!</h2><p>Tu suscripción de Norem ya está activa. Ya puedes seguir usando todas las herramientas de tu negocio.</p>")


def enviar_prueba_vencida(destinatario: str, nombre: str) -> bool:
    enlace = f"{BASE_URL}/admin/suscripcion"
    return enviar_email_base(destinatario, "Tu prueba de Norem finalizó", f"<h2>Hola {nombre}, tu prueba de 14 días finalizó.</h2><p>Tu información está resguardada. Activa tu suscripción para continuar usando Norem.</p><p><a href='{enlace}'>Continuar con Norem</a></p>")

def generar_url_mapa(direccion):
    if not direccion or direccion.strip().lower() in {"taller", "local"}:
        return None
    return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(direccion.strip())}"


def debe_enviar_ubicacion_google(agendamiento) -> bool:
    """La ubicación solo se comparte si el negocio la habilitó explícitamente."""
    try:
        tenant = getattr(agendamiento, "tenant", None)
        config = json.loads(getattr(tenant, "config_json", "") or "{}")
        return bool(config.get("notificaciones", {}).get("enviar_ubicacion_google", False))
    except (TypeError, ValueError, json.JSONDecodeError):
        return False

def enviar_solicitud_confirmacion(agendamiento):
    """ PASO 1 AUTOMÁTICO: Envía el botón de confirmación """
    url_confirmar = f"{BASE_URL}/cliente/confirmar/{agendamiento.id}"
    url_rechazar = f"{BASE_URL}/cliente/rechazar/{agendamiento.id}" # Opcional: añadir esta ruta

    asunto = f"⚠️ Acción Requerida: Confirma tu cita - {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}"
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <div style="display: inline-block; width: 60px; height: 60px; line-height: 60px; border-radius: 50%; background-color: #e6f7ed; color: #10b981; font-size: 32px; font-weight: bold; text-align: center; margin-bottom: 15px;">✓</div>
                                    <h2 style="color:#1e293b; margin: 0 0 5px 0; letter-spacing: 1px;">NOREM</h2>
                                    <p style="color:#64748b; font-size:12px; margin:0; text-transform: uppercase;">Sistema de Agendamiento</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px; text-align: center;">
                                    <h3 style="color:#1e293b; font-size:20px; margin-bottom:10px;">¿Confirmas tu asistencia?</h3>
                                    <p style="color:#475569; font-size:16px; line-height:1.6;">
                                        Hola <strong>{agendamiento.nombre}</strong>, para asegurar el cupo de tu <strong>{f"{agendamiento.marca} ({agendamiento.patente})" if agendamiento.tenant_id != "womenlashcl" else "servicio"}</strong> este {agendamiento.fecha_inicio.strftime('%d/%m')}, pulsa el botón:
                                    </p>
                                    <div style="margin-top: 35px;">
                                        <a href="{url_confirmar}" style="background-color:#10b981; color:#ffffff; padding:18px 35px; text-decoration:none; border-radius:8px; font-weight:bold; font-size:18px; display:inline-block; box-shadow: 0 4px 6px rgba(16,185,129,0.2);">✅ SÍ, CONFIRMO MI HORA</a>
                                    </div>
                                    <p style="color:#94a3b8; font-size:12px; margin-top:30px;">Si no puedes asistir, por favor ignora este correo para liberar el cupo.</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color:#f8fafc; padding:20px; text-align:center; color:#94a3b8; font-size:11px;">
                                    Este es un mensaje automático de Norem.
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    return enviar_email_base(agendamiento.correo, f"⚠️ Acción Requerida: Confirma tu cita - {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}", contenido_html)

def enviar_aviso_accion_al_dueno(agendamiento, accion):
    """ Notifica al dueño qué hizo el cliente (ACEPTADA / RECHAZADA) """
    asunto = f"📢 CITA {accion}: {agendamiento.nombre} - {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}"
    # Color dinámico: Verde si acepta, Rojo si rechaza
    color_status = "#10b981" if "ACEPTADA" in accion or "CONFIRMADA" in accion else "#ef4444"
    servicio_label = "Local" if getattr(agendamiento, 'subtipo', '').lower() == "taller" else getattr(agendamiento, 'subtipo', '').capitalize() or "Servicio"
    
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f1f5f9; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 30px 0;">
                <tr>
                    <td align="center">
                        <table width="550" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:12px; overflow:hidden; border: 1px solid #e2e8f0;">
                            <tr>
                                <td style="background-color:#1e293b; padding:20px; text-align:center;">
                                    <div style="display: inline-block; width: 50px; height: 50px; line-height: 50px; border-radius: 50%; background-color: rgba(255,255,255,0.15); color: #10b981; font-size: 28px; font-weight: bold; text-align: center; margin-bottom: 10px;">✓</div>
                                    <h2 style="color:#ffffff; margin:0; font-size:18px; letter-spacing:1px;">REPORTE DE SISTEMA</h2>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:30px;">
                                    <div style="text-align:center; margin-bottom:25px;">
                                        <span style="background-color:{color_status}; color:white; padding:8px 15px; border-radius:20px; font-weight:bold; font-size:14px;">
                                            ESTADO: {accion}
                                        </span>
                                    </div>
                                    <table width="100%" style="color:#334155; font-size:15px; border-collapse:collapse;">
                                        <tr><td style="padding:8px 0; border-bottom:1px solid #f1f5f9;"><strong>Cliente:</strong></td><td style="text-align:right;">{agendamiento.nombre} {agendamiento.apellido}</td></tr>
                                        <tr><td style="padding:8px 0; border-bottom:1px solid #f1f5f9;"><strong>Vehículo:</strong></td><td style="text-align:right;">{agendamiento.marca} {agendamiento.modelo}</td></tr>
                                        {"" if agendamiento.tenant_id == "womenlashcl" else f"<tr><td style='padding:8px 0; border-bottom:1px solid #f1f5f9;'><strong>Patente:</strong></td><td style='text-align:right;'>{agendamiento.patente}</td></tr>"}
                                        <tr><td style="padding:8px 0; border-bottom:1px solid #f1f5f9;"><strong>Fecha/Hora:</strong></td><td style="text-align:right;">{agendamiento.fecha_inicio.strftime('%d-%m-%Y %H:%M')}</td></tr>
                                        <tr><td style="padding:8px 0; border-bottom:1px solid #f1f5f9;"><strong>Servicio:</strong></td><td style="text-align:right;">{servicio_label}</td></tr>
                                    </table>
                                    <div style="margin-top:25px; background-color:#f8fafc; padding:15px; border-radius:8px; font-size:13px; color:#64748b; text-align:center;">
                                        La base de datos ha sido actualizada automáticamente.
                                    </div>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    return enviar_email_base(CORREO_LOCAL, asunto, contenido_html)

def enviar_confirmacion_agendamiento(agendamiento, nota_compartida):
    """ PASO 2 AUTOMÁTICO: Envía el calendario una vez confirmado """
    url_mapa = generar_url_mapa(getattr(agendamiento, 'direccion', '')) if debe_enviar_ubicacion_google(agendamiento) else None
    ubicacion_html = ""
    if url_mapa:
        ubicacion_html = f"""
            <p style=\"margin:5px 0; color:#1e293b;\">📍 <strong>Ubicación:</strong> {getattr(agendamiento, 'direccion', '')}</p>
            <div style=\"text-align:center; margin-top:18px;\">
                <a href=\"{url_mapa}\" style=\"background-color:#2563eb; color:#ffffff; padding:12px 25px; text-decoration:none; border-radius:6px; font-weight:bold; display:inline-block; font-size:14px;\">📍 VER UBICACIÓN EN GOOGLE MAPS</a>
            </div>
        """
    asunto = f"✅ ¡Confirmado! Todo listo para tu cita - {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}"
    
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <div style="display: inline-block; width: 60px; height: 60px; line-height: 60px; border-radius: 50%; background-color: #e6f7ed; color: #10b981; font-size: 32px; font-weight: bold; text-align: center;">✓</div>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:0 40px 40px 40px;">
                                    <h2 style="color:#1e293b; text-align:center; margin-bottom:20px;">¡Cita Confirmada!</h2>
                                    <p style="color:#475569; text-align:center;">Hola {agendamiento.nombre}, tu cita ha sido agendada con éxito. Aquí tienes los detalles:</p>
                                    
                                    <div style="background-color:#f8fafc; border-radius:10px; padding:20px; margin:25px 0;">
                                        <p style="margin:5px 0; color:#1e293b;">📅 <strong>Día:</strong> {agendamiento.fecha_inicio.strftime('%d de %B, %Y')}</p>
                                        <p style="margin:5px 0; color:#1e293b;">🕒 <strong>Hora:</strong> {agendamiento.fecha_inicio.strftime('%H:%M')} hrs</p>
                                        {ubicacion_html}
                                    </div>
                                    
                                    <p style="color:#64748b; font-size:14px; text-align:center; margin-top:30px;">
                                        <em>"{nota_compartida}"</em>
                                    </p>
                                    <p style="color:#94a3b8; font-size:12px; text-align:center; margin-top:20px; border-top:1px solid #f1f5f9; padding-top:20px;">
                                        Hemos adjuntado un archivo de calendario a este correo para que puedas agregarlo a tu teléfono.
                                    </p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    
    # Crear archivo .ics
    cal = vobject.iCalendar()
    vevent = cal.add('vevent')
    vevent.add('summary').value = f"Cita: {agendamiento.nombre} {agendamiento.apellido}" if agendamiento.tenant_id == "womenlashcl" else f"Mantención: {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}"
    vevent.add('dtstart').value = agendamiento.fecha_inicio
    vevent.add('dtend').value = agendamiento.fecha_termino
    
    return enviar_email_base(
        agendamiento.correo, 
        asunto, 
        contenido_html, 
        adjunto_path=cal.serialize().encode('utf-8'), 
        adjunto_name=f"cita_{agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}.ics"
    )

def enviar_correo_cancelacion(agendamiento):
    asunto = f"❌ Tu cita ha sido cancelada - {agendamiento.patente if agendamiento.tenant_id != 'womenlashcl' else agendamiento.nombre}"
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <div style="display: inline-block; width: 60px; height: 60px; line-height: 60px; border-radius: 50%; background-color: #fde8e8; color: #ef4444; font-size: 32px; font-weight: bold; text-align: center;">✗</div>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 0 40px 40px 40px; text-align: center;">
                                    <h2 style="color:#ef4444;">Cita Cancelada</h2>
                                    <p style="color:#475569;">Hola {agendamiento.nombre}, te informamos que tu cita para el <strong>{agendamiento.fecha_inicio.strftime('%d-%m-%Y')}</strong> a las <strong>{agendamiento.fecha_inicio.strftime('%H:%M')} hrs</strong> ha sido cancelada.</p>
                                    <p style="color:#64748b; font-size:14px; margin-top:20px;">Si consideras que esto es un error o deseas reagendar, por favor contáctanos.</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    return enviar_email_base(agendamiento.correo, asunto, contenido_html)


def enviar_correo_cancelacion_por_bloqueo(agendamiento, motivo: str = None) -> bool:
    """Informa un cierre de día y entrega un enlace para que el cliente reagende."""
    tipo = agendamiento.tipo_servicio.value if hasattr(agendamiento.tipo_servicio, "value") else str(agendamiento.tipo_servicio)
    parametros = {"tipo": tipo}
    if getattr(agendamiento, "subtipo", None):
        parametros["subtipo"] = "local" if agendamiento.subtipo == "taller" else agendamiento.subtipo
    if tipo == "especializado" and getattr(agendamiento, "duracion_horas", None):
        parametros["duracion_horas"] = agendamiento.duracion_horas
    enlace_reagendar = f"{BASE_URL}/cliente/agendar_web?{urllib.parse.urlencode(parametros)}"
    detalle_motivo = f" Motivo informado: {motivo}." if motivo else ""
    asunto = f"Actualización importante sobre tu cita del {agendamiento.fecha_inicio.strftime('%d/%m')}"
    contenido_html = f"""
    <html><body style="margin:0;padding:0;background:#f1f5f9;font-family:Arial,sans-serif;color:#0f172a;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="padding:40px 16px;"><tr><td align="center">
        <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;background:#fff;border-radius:18px;overflow:hidden;box-shadow:0 10px 28px rgba(15,23,42,.10);">
          <tr><td style="background:#0755bf;padding:28px;text-align:center;"><div style="color:#fff;font-size:20px;font-weight:800;letter-spacing:4px;">NOREM</div></td></tr>
          <tr><td style="padding:36px;"><h1 style="margin:0 0 16px;font-size:24px;color:#0f172a;">Tu cita fue cancelada</h1>
            <p style="margin:0 0 16px;color:#475569;line-height:1.6;">Hola {agendamiento.nombre}, el día <strong>{agendamiento.fecha_inicio.strftime('%d de %B')}</strong> no estará disponible, por lo que tuvimos que cancelar tu cita de las <strong>{agendamiento.fecha_inicio.strftime('%H:%M')} hrs</strong>.{detalle_motivo}</p>
            <p style="margin:0 0 26px;color:#475569;line-height:1.6;">Puedes elegir un nuevo horario disponible desde aquí:</p>
            <p style="text-align:center;margin:0 0 25px;"><a href="{enlace_reagendar}" style="display:inline-block;background:#0755bf;color:#fff;padding:14px 24px;border-radius:10px;font-weight:700;text-decoration:none;">Reagendar mi cita</a></p>
            <p style="margin:0;color:#64748b;font-size:13px;line-height:1.5;">Lamentamos los inconvenientes. Si necesitas ayuda, responde o contacta directamente a tu negocio.</p>
          </td></tr><tr><td style="background:#f8fafc;padding:18px;text-align:center;color:#64748b;font-size:12px;">Este es un mensaje automático de Norem.</td></tr>
        </table></td></tr></table>
    </body></html>
    """
    return enviar_email_base(agendamiento.correo, asunto, contenido_html)

def procesar_flujo_automatico():
    db = SessionLocal()
    ahora = get_now_chile()
    hace_5_min = ahora - timedelta(minutes=5)

    # Buscamos citas PENDIENTES, creadas hace más de 5 min, a las que aún no se les envió el botón
    nuevas = db.query(Agendamiento).filter(
        Agendamiento.estado == "pendiente",
        Agendamiento.creado_en <= hace_5_min,
        Agendamiento.boton_enviado == False
    ).all()

    print(f"DEBUG scheduler: ahora={ahora}, corte={hace_5_min}. Encontradas para enviar botón: {len(nuevas)}")

    for cita in nuevas:
        print(f"  → Procesando cita ID {cita.id} ({cita.nombre}, creada: {cita.creado_en})")
        if enviar_solicitud_confirmacion(cita):
            cita.boton_enviado = True
            db.commit()
            print(f"  ✅ Botón de confirmación enviado para cita ID: {cita.id}")
        else:
            print(f"  ❌ Falló el envío del botón para cita ID: {cita.id}")

    db.close()


def enviar_aviso_recibido_cliente(agendamiento):
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden;">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <div style="display: inline-block; width: 60px; height: 60px; line-height: 60px; border-radius: 50%; background-color: #e6f7ed; color: #10b981; font-size: 32px; font-weight: bold; text-align: center;">✓</div>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 0 40px 40px 40px; text-align: center;">
                                    <h2 style="color:#1e293b;">¡Solicitud Recibida!</h2>
                                    <p style="color:#475569;">Hola {agendamiento.nombre}, hemos recibido tu solicitud para el {agendamiento.fecha_inicio.strftime('%d-%m-%Y')}.</p>
                                    <div style="background-color:#f1f5f9; border-left:4px solid #2563eb; padding:15px; margin:20px 0; text-align:left;">
                                        <p style="margin:0; font-size:14px;"><strong>IMPORTANTE:</strong> En 5 minutos te enviaremos un <strong>segundo correo</strong> con un botón para confirmar definitivamente tu cupo.</p>
                                    </div>
                                    <p style="color:#64748b; font-size:14px;">¡Gracias por confiar en nosotros!</p>
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    return enviar_email_base(agendamiento.correo, "📨 Recibimos tu solicitud - Norem", contenido_html)
