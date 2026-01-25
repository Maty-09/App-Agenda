import yagmail
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")


def enviar_correo_confirmacion(destinatario, asunto, contenido):
    yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)
    yag.send(
        to=destinatario,
        subject=asunto,
        contents=contenido
    )


def enviar_correo_cancelacion(agendamiento):
    """
    Envía correo cuando una mantención es cancelada por el administrador
    """
    asunto = "❌ Mantención cancelada"

    contenido = f"""
Hola {agendamiento.nombre},

Te informamos que tu mantención fue cancelada por nuestro equipo.

📅 Fecha: {agendamiento.fecha_inicio.strftime('%d-%m-%Y')}
🕒 Hora: {agendamiento.fecha_inicio.strftime('%H:%M')}
🚗 Patente: {agendamiento.patente}

Si necesitas reagendar, puedes hacerlo desde nuestra web
o contactarnos directamente.

Saludos,
Equipo Mantenciones
"""

    enviar_correo_confirmacion(
        agendamiento.correo,
        asunto,
        contenido
    )