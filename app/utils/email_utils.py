import os
import smtplib
import vobject
from datetime import datetime, timedelta
from dotenv import load_dotenv
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import urllib.parse
from app.database import SessionLocal 
from app.models import Agendamiento, get_now_chile

load_dotenv()

# --- CONFIGURACIÓN GLOBAL ---
REMITENTE = os.getenv("EMAIL_SENDER", "agendamiento.localdemo@gmail.com")
PASSWORD = os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_TOKEN")
CORREO_LOCAL = os.getenv("EMAIL_ADMIN", "matiasduranm09@gmail.com")
# IMPORTANTE: Cambia esto a tu URL de Render cuando subas el proyecto
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
LOGO_URL = os.getenv("LOGO_URL", "https://static.wixstatic.com/media/63336e_1df8bf9a9c1542f2ba703877a908b01d~mv2.webp")

def enviar_email_base(destinatario, asunto, contenido_html, adjunto_path=None, adjunto_name=None):
    """Función maestra para enviar correos y evitar repetir código de login"""
    msg = MIMEMultipart()
    msg['From'] = REMITENTE
    msg['To'] = destinatario
    msg['Subject'] = asunto
    msg.attach(MIMEText(contenido_html, 'html'))

    if adjunto_path:
        part = MIMEBase('application', "octet-stream")
        part.set_payload(adjunto_path)
        encoders.encode_base64(part)
        part.add_header('Content-Disposition', f'attachment; filename="{adjunto_name}"')
        msg.attach(part)

    if not REMITENTE or not PASSWORD:
        print("❌ No se puede enviar correo: revisa EMAIL_SENDER y EMAIL_PASSWORD / EMAIL_TOKEN en el .env")
        return False

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(REMITENTE, PASSWORD)
            server.sendmail(REMITENTE, destinatario, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ Error SMTP: {e}")
        return False

def generar_url_mapa(direccion):
    direccion_busqueda = direccion if (direccion and "taller" not in direccion.lower() and "local" not in direccion.lower()) else "Tu Direccion Real, Ciudad, Chile"
    encoded_dir = urllib.parse.quote(direccion_busqueda)
    return f"https://www.google.com/maps/search/?api=1&query={encoded_dir}"

def enviar_solicitud_confirmacion(agendamiento):
    """ PASO 1 AUTOMÁTICO: Envía el botón de confirmación """
    url_confirmar = f"{BASE_URL}/cliente/confirmar/{agendamiento.id}"
    url_rechazar = f"{BASE_URL}/cliente/rechazar/{agendamiento.id}" # Opcional: añadir esta ruta

    asunto = f"⚠️ Acción Requerida: Confirma tu cita - {agendamiento.patente}"
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            <tr>
                                <td align="center" style="padding: 30px 0 10px 0;">
                                    <img src="{LOGO_URL}" alt="Local" width="80" style="display:block; border:0;">
                                    <h2 style="color:#1e293b; margin: 15px 0 5px 0; letter-spacing: 1px;">LOCAL</h2>
                                    <p style="color:#64748b; font-size:12px; margin:0; text-transform: uppercase;">Sistema de Agendamiento</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="padding: 40px; text-align: center;">
                                    <h3 style="color:#1e293b; font-size:20px; margin-bottom:10px;">¿Confirmas tu asistencia?</h3>
                                    <p style="color:#475569; font-size:16px; line-height:1.6;">
                                        Hola <strong>{agendamiento.nombre}</strong>, para asegurar el cupo de tu <strong>{agendamiento.marca} ({agendamiento.patente})</strong> este {agendamiento.fecha_inicio.strftime('%d/%m')}, pulsa el botón:
                                    </p>
                                    <div style="margin-top: 35px;">
                                        <a href="{url_confirmar}" style="background-color:#10b981; color:#ffffff; padding:18px 35px; text-decoration:none; border-radius:8px; font-weight:bold; font-size:18px; display:inline-block; box-shadow: 0 4px 6px rgba(16,185,129,0.2);">✅ SÍ, CONFIRMO MI HORA</a>
                                    </div>
                                    <p style="color:#94a3b8; font-size:12px; margin-top:30px;">Si no puedes asistir, por favor ignora este correo para liberar el cupo.</p>
                                </td>
                            </tr>
                            <tr>
                                <td style="background-color:#f8fafc; padding:20px; text-align:center; color:#94a3b8; font-size:11px;">
                                    Este es un mensaje automático del Sistema de Agendamiento.
                                </td>
                            </tr>
                        </table>
                    </td>
                </tr>
            </table>
        </body>
    </html>
    """
    return enviar_email_base(agendamiento.correo, f"⚠️ Acción Requerida: Confirma tu cita - {agendamiento.patente}", contenido_html)

def enviar_aviso_accion_al_dueno(agendamiento, accion):
    """ Notifica al dueño qué hizo el cliente (ACEPTADA / RECHAZADA) """
    asunto = f"📢 CITA {accion}: {agendamiento.nombre} - {agendamiento.patente}"
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
                                    <img src="{LOGO_URL}" width="50" style="margin-bottom:10px;">
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
                                        <tr><td style="padding:8px 0; border-bottom:1px solid #f1f5f9;"><strong>Patente:</strong></td><td style="text-align:right;">{agendamiento.patente}</td></tr>
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
    url_mapa = generar_url_mapa(getattr(agendamiento, 'direccion', ''))
    asunto = f"✅ ¡Confirmado! Todo listo para tu cita - {agendamiento.patente}"
    
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 10px 25px rgba(0,0,0,0.05);">
                            <tr>
                                <td align="center" style="padding: 30px 0;">
                                    <img src="{LOGO_URL}" width="70">
                                </td>
                            </tr>
                            <tr>
                                <td style="padding:0 40px 40px 40px;">
                                    <h2 style="color:#1e293b; text-align:center; margin-bottom:20px;">¡Cita Confirmada!</h2>
                                    <p style="color:#475569; text-align:center;">Hola {agendamiento.nombre}, tu cita ha sido agendada con éxito. Aquí tienes los detalles:</p>
                                    
                                    <div style="background-color:#f8fafc; border-radius:10px; padding:20px; margin:25px 0;">
                                        <p style="margin:5px 0; color:#1e293b;">📅 <strong>Día:</strong> {agendamiento.fecha_inicio.strftime('%d de %B, %Y')}</p>
                                        <p style="margin:5px 0; color:#1e293b;">🕒 <strong>Hora:</strong> {agendamiento.fecha_inicio.strftime('%H:%M')} hrs</p>
                                        <p style="margin:5px 0; color:#1e293b;">📍 <strong>Ubicación:</strong> {getattr(agendamiento, 'direccion', 'Local')}</p>
                                    </div>

                                    <div style="text-align:center;">
                                        <a href="{url_mapa}" style="background-color:#2563eb; color:#ffffff; padding:12px 25px; text-decoration:none; border-radius:6px; font-weight:bold; display:inline-block; font-size:14px;">📍 VER UBICACIÓN EN MAPA</a>
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
    vevent.add('summary').value = f"Mantención: {agendamiento.patente}"
    vevent.add('dtstart').value = agendamiento.fecha_inicio
    vevent.add('dtend').value = agendamiento.fecha_termino
    
    return enviar_email_base(
        agendamiento.correo, 
        asunto, 
        contenido_html, 
        adjunto_path=cal.serialize().encode('utf-8'), 
        adjunto_name=f"cita_{agendamiento.patente}.ics"
    )

def enviar_correo_cancelacion(agendamiento):
    asunto = f"❌ Tu cita ha sido cancelada - {agendamiento.patente}"
    contenido_html = f"""
    <html>
        <body style="margin:0; padding:0; background-color:#f4f7f6; font-family: 'Segoe UI', Arial, sans-serif;">
            <table width="100%" border="0" cellspacing="0" cellpadding="0" style="padding: 40px 0;">
                <tr>
                    <td align="center">
                        <table width="500" border="0" cellspacing="0" cellpadding="0" style="background-color:#ffffff; border-radius:15px; overflow:hidden; box-shadow: 0 4px 12px rgba(0,0,0,0.1);">
                            <tr>
                                <td align="center" style="padding: 30px 0;">
                                    <img src="{LOGO_URL}" alt="Local" width="60">
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

def procesar_flujo_automatico():
    db = SessionLocal()
    ahora = get_now_chile() # Usamos la misma zona horaria que creado_en
    hace_5_min = ahora - timedelta(minutes=5)
    inicio_hoy = ahora.replace(hour=0, minute=0, second=0, microsecond=0)

    # Solo buscamos citas de HOY, que sean PENDIENTES y tengan más de 5 min
    nuevas = db.query(Agendamiento).filter(
        Agendamiento.estado == "pendiente",
        Agendamiento.creado_en <= hace_5_min,
        Agendamiento.creado_en >= inicio_hoy, # <--- Filtro para no ver lo de ayer
        Agendamiento.nota_interna == None
    ).all()

    print(f"DEBUG: Buscando entre {inicio_hoy} y {hace_5_min}. Encontradas: {len(nuevas)}")

    for cita in nuevas:
        if enviar_solicitud_confirmacion(cita):
            cita.nota_interna = "BOTON_ENVIADO"
            db.commit()
            print(f"✅ Botón enviado para cita ID: {cita.id}")
    
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
                                <td align="center" style="padding: 30px 0;">
                                    <img src="{LOGO_URL}" alt="Local" width="60">
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
    return enviar_email_base(agendamiento.correo, "📨 Recibimos tu solicitud - Local", contenido_html)