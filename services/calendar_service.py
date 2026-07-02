import datetime
import os.path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Scope de Calendar para crear y ver eventos
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def obtener_servicio_calendario():
    """
    Obtiene y retorna el servicio de la API de Google Calendar usando autenticación de usuario local.
    """
    creds = None
    # El archivo token.json almacena los tokens de acceso y refresco
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if os.path.exists("credentials.json"):
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_local_server(port=0)
                # Guardamos los credenciales
                with open("token.json", "w") as token:
                    token.write(creds.to_json())
            else:
                print("⚠️ ATENCIÓN: Falta el archivo credentials.json de Google Cloud en el directorio raíz.")
                return None

    try:
        service = build("calendar", "v3", credentials=creds)
        return service
    except HttpError as error:
        print(f"Error en Google Calendar: {error}")
        return None

def agendar_evento(nombre: str, dia: str, hora: str, correo: str):
    """
    Crea un evento en Google Calendar. Retorna True si tiene éxito.
    """
    service = obtener_servicio_calendario()
    if not service:
        print("No se pudo conectar a Google Calendar. Revise sus credenciales.")
        return False
        
    # En un sistema real se usa un parseador de fechas (ej: dateutil)
    # Aquí aproximamos la fecha para la prueba de concepto
    try:
        from datetime import datetime, timedelta
        hoy = datetime.now()
        # Parseamos la hora aproximada (ej: si escribieron "09:00" o "15:00")
        h = int(hora.split(":")[0]) if ":" in hora else 9
        inicio = hoy.replace(hour=h, minute=0, second=0).isoformat() + "-04:00"
        fin = (hoy.replace(hour=h, minute=0, second=0) + timedelta(hours=1)).isoformat() + "-04:00"
    except:
        inicio = "2024-01-01T09:00:00-04:00"
        fin = "2024-01-01T10:00:00-04:00"

    event = {
        'summary': f'Cita de {nombre}',
        'location': 'Atención Virtual',
        'description': f'Reserva confirmada vía WhatsApp para {nombre} (RUT pendiente) ({correo}).\nAgendado para: {dia} a las {hora}.',
        'start': {
            'dateTime': inicio,
            'timeZone': 'America/Santiago',
        },
        'end': {
            'dateTime': fin,
            'timeZone': 'America/Santiago',
        },
        'attendees': [
            {'email': correo},
        ],
        'reminders': {
            'useDefault': False,
            'overrides': [
                {'method': 'email', 'minutes': 24 * 60},
                {'method': 'popup', 'minutes': 10},
            ],
        },
    }

    try:
        event = service.events().insert(calendarId='primary', body=event).execute()
        print(f"Evento creado exitosamente: {event.get('htmlLink')}")
        return True
    except HttpError as error:
        print(f"Error al intentar crear el evento: {error}")
        return False
