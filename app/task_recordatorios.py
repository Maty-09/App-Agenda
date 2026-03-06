import os
import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
from app.database import SessionLocal  # Importa tu conexión a la DB
from app.models import Agendamiento    # Importa tu modelo

def enviar_correo_recordatorio(cliente_email, nombre, fecha, hora, patente):
    REMITENTE = "agendamiento.tommycrozier@gmail.com"
    PASSWORD = "evvg megi vlgp gbds"

    asunto = f"⏰ Recordatorio: Tu mantención es mañana ({patente})"
    
    html = f"""
    <html>
        <body style="font-family: sans-serif; line-height: 1.6;">
            <div style="max-width: 500px; border: 1px solid #ddd; padding: 20px; border-radius: 10px;">
                <h2 style="color: #2563eb;">¡Hola {nombre}!</h2>
                <p>Te recordamos que tienes una cita agendada para mañana:</p>
                <p style="font-size: 18px; background: #f0f4ff; padding: 10px; border-radius: 5px; text-align: center;">
                    📅 <b>{fecha}</b> a las <b>{hora} hrs</b>
                </p>
                <p>🚗 <b>Vehículo:</b> {patente}</p>
                <hr>
                <p>Si tienes algún inconveniente para asistir, por favor contáctanos lo antes posible respondiendo a este correo.</p>
                <p>Saludos,<br><b>Equipo Tommy Crozier</b></p>
            </div>
        </body>
    </html>
    """

    msg = MIMEMultipart()
    msg['From'] = REMITENTE
    msg['To'] = cliente_email
    msg['Subject'] = asunto
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(REMITENTE, PASSWORD)
            server.sendmail(REMITENTE, cliente_email, msg.as_string())
        return True
    except Exception as e:
        print(f"Error enviando recordatorio a {cliente_email}: {e}")
        return False

def procesar_agendamientos_manana():
    db = SessionLocal()
    try:
        # Calculamos el rango de "mañana"
        manana = datetime.now() + timedelta(days=1)
        inicio_manana = manana.replace(hour=0, minute=0, second=0, microsecond=0)
        fin_manana = manana.replace(hour=23, minute=59, second=59, microsecond=999)

        # Buscamos citas para mañana que no estén canceladas
        citas = db.query(Agendamiento).filter(
            Agendamiento.fecha_inicio >= inicio_manana,
            Agendamiento.fecha_inicio <= fin_manana,
            Agendamiento.estado != "cancelado"
        ).all()

        print(f"[{datetime.now()}] Revisando recordatorios... Encontrados: {len(citas)}")

        for cita in citas:
            fecha_str = cita.fecha_inicio.strftime('%d-%m-%Y')
            hora_str = cita.fecha_inicio.strftime('%H:%M')
            
            exito = enviar_correo_recordatorio(
                cita.correo, 
                cita.nombre, 
                fecha_str, 
                hora_str, 
                cita.patente
            )
            if exito:
                print(f"✅ Recordatorio enviado a {cita.correo} para la cita de las {hora_str}")

    finally:
        db.close()

if __name__ == "__main__":
    procesar_agendamientos_manana()