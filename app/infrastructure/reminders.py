from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import pytz
from app.core.database import SessionLocal
from app.core.models import Agendamiento
from app.infrastructure.twilio_service import generar_respuesta_twilio
# Para enviar realmente se usaría client.messages.create de Twilio, 
# asumiendo que twilio_service.py tiene inicializado el cliente.
import os
from twilio.rest import Client

def enviar_recordatorios_manana():
    """
    Busca todas las citas de mañana y les envía un recordatorio por WhatsApp.
    """
    tz = pytz.timezone('America/Santiago')
    hoy = datetime.now(tz).replace(tzinfo=None)
    manana = hoy + timedelta(days=1)
    
    inicio_manana = manana.replace(hour=0, minute=0, second=0)
    fin_manana = manana.replace(hour=23, minute=59, second=59)
    
    db = SessionLocal()
    try:
        citas = db.query(Agendamiento).filter(
            Agendamiento.fecha_inicio >= inicio_manana,
            Agendamiento.fecha_inicio <= fin_manana,
            Agendamiento.estado == "CONFIRMADA" # O el estado que manejes
        ).all()
        
        if not citas:
            print("No hay citas para mañana.")
            return

        # Inicializar Twilio
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        twilio_number = os.getenv("TWILIO_WHATSAPP_NUMBER", "whatsapp:+14155238886")
        
        if not account_sid or not auth_token:
            print("No hay credenciales de Twilio configuradas para recordatorios.")
            return
            
        client = Client(account_sid, auth_token)
        
        for cita in citas:
            # Formatear el teléfono
            num = cita.telefono
            if not num.startswith("+"):
                num = f"+56{num}"
                
            mensaje = (
                f"Hola {cita.nombre}, te recordamos que mañana tienes una cita agendada "
                f"a las {cita.fecha_inicio.strftime('%H:%M')} hrs para servicio de {cita.marca}. "
                "¡Te esperamos!"
            )
            
            try:
                client.messages.create(
                    body=mensaje,
                    from_=twilio_number,
                    to=f"whatsapp:{num}"
                )
                print(f"Recordatorio enviado a {cita.nombre} ({num})")
            except Exception as e:
                print(f"Error enviando a {num}: {e}")
                
    finally:
        db.close()

if __name__ == "__main__":
    print("Iniciando envío de recordatorios...")
    enviar_recordatorios_manana()
    print("Finalizado.")
