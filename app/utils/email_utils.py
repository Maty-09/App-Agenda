import yagmail
import os
from dotenv import load_dotenv

load_dotenv()

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASS = os.getenv("EMAIL_PASS")

def enviar_correo_confirmacion(destinatario, asunto, contenido):
    yag = yagmail.SMTP(EMAIL_USER, EMAIL_PASS)
    yag.send(to=destinatario, subject=asunto, contents=contenido)
