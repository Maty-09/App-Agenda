from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from app.infrastructure.bot_logic import obtener_reserva_pendiente, confirmar_reserva
import urllib.parse

router = APIRouter()

@router.get("/confirmar/{token}", response_class=HTMLResponse)
async def confirmar_cita_email(token: str):
    """
    Endpoint que se llama cuando el usuario hace clic en el enlace del correo.
    """
    reserva = obtener_reserva_pendiente(token)
    
    if not reserva:
        return """
        <html>
            <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
                <h1 style="color: red;">Error: Enlace Inválido o Expirado</h1>
                <p>No pudimos encontrar la reserva asociada a este enlace. Es posible que ya haya sido confirmada o que el tiempo haya expirado.</p>
            </body>
        </html>
        """
        
    # Actualizar el estado de la reserva para no procesarla dos veces
    confirmar_reserva(token)
    
    # Crear un enlace directo de Google Calendar para que el usuario lo agregue sin usar APIs
    # Como la hora y el día vienen como texto libre (ej: "Lunes", "15:00"), 
    # dejamos la fecha vacía o genérica para que el usuario la ajuste en su calendario si es necesario.
    # En un sistema real, estas fechas se parsean a formato YYYYMMDDTHHMMSSZ
    titulo = urllib.parse.quote(f"Cita Agendada: {reserva['nombre']}")
    detalles = urllib.parse.quote(f"Reserva para el día {reserva['dia']} a las {reserva['hora']}.\\n\\nRUT: {reserva['rut']}\\nCorreo: {reserva['correo']}")
    
    google_calendar_url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={titulo}&details={detalles}"
    
    return f"""
    <html>
        <body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px; background-color: #f4f4f9;">
            <div style="background: white; max-width: 600px; margin: auto; padding: 30px; border-radius: 10px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
                <h1 style="color: #4CAF50;">¡Cita Confirmada Exitosamente! ✅</h1>
                <p style="font-size: 18px;">Hola <strong>{reserva['nombre']}</strong>,</p>
                <p style="font-size: 18px;">Tu cita para el <strong>{reserva['dia']}</strong> a las <strong>{reserva['hora']}</strong> ha sido confirmada en nuestro sistema.</p>
                
                <a href="{google_calendar_url}" target="_blank" style="display: inline-block; margin-top: 20px; padding: 12px 25px; background-color: #4285F4; color: white; text-decoration: none; border-radius: 5px; font-weight: bold;">📅 Agregar a mi Google Calendar</a>
                
                <p style="color: #666; margin-top: 30px;">¡Te esperamos!</p>
            </div>
        </body>
    </html>
    """
