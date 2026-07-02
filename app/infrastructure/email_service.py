import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import uuid
import os
from dotenv import load_dotenv

# Cargar variables desde el archivo .env existente
load_dotenv()

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

SENDER_EMAIL = os.getenv("EMAIL_SENDER")
SENDER_PASSWORD = os.getenv("EMAIL_PASSWORD") or os.getenv("EMAIL_TOKEN")

# Usar Ngrok o localhost según esté configurado
NGROK_URL = os.getenv("BASE_URL", "http://localhost:8000")

def enviar_correo_confirmacion(destinatario: str, nombre: str, dia: str, hora: str, token: str):
    """
    Envía un correo electrónico con un enlace único para confirmar la reserva.
    """
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = destinatario
    msg['Subject'] = "Confirma tu Reserva de Cita"

    url_confirmacion = f"{NGROK_URL}/api/confirmar/{token}"

    html = f"""
    <html>
      <body>
        <h2>Hola {nombre},</h2>
        <p>Has solicitado agendar una cita para el día <strong>{dia}</strong> a las <strong>{hora}</strong>.</p>
        <p>Para confirmar tu cita y agendarla de forma definitiva, por favor haz clic en el siguiente enlace:</p>
        <p><a href="{url_confirmacion}" style="display: inline-block; padding: 10px 20px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 5px; margin-top: 10px; margin-bottom: 10px;">Confirmar Reserva</a></p>
        <br>
        <p><em>Si no solicitaste esto, puedes ignorar este correo.</em></p>
      </body>
    </html>
    """
    
    msg.attach(MIMEText(html, 'html'))

    try:
        server = smtplib.SMTP_SSL(SMTP_SERVER, 465)
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()
        print(f"Correo enviado exitosamente a {destinatario}")
    except Exception as e:
        print(f"Error enviando correo: {e}")

def generar_token() -> str:
    return str(uuid.uuid4())
