from app.core.database import SessionLocal
from app.domain_ai.services import chat_ia

# Mantener compatibilidad con funciones previas que puedan importar esto
sesiones_usuarios = {}
reservas_pendientes = {} 

def obtener_reserva_pendiente(token: str):
    return None

def confirmar_reserva(token: str):
    return False

async def generar_respuesta_bot(texto: str, numero_remitente: str, tenant_id: str) -> str:
    """
    Nuevo generador de respuestas potenciado por Inteligencia Artificial.
    Reemplaza la máquina de estados antigua.
    """
    # Limpiamos el número por si viene como "whatsapp:+56912345678"
    telefono_limpio = numero_remitente.replace("whatsapp:", "").replace("+56", "").replace("+", "").strip()
    
    db = SessionLocal()
    try:
        # Llamar directamente a la Inteligencia Artificial pasándole la base de datos para contexto
        respuesta = chat_ia(mensaje=texto, db=db, telefono=telefono_limpio, tenant_id=tenant_id)
        return respuesta
    except Exception as e:
        return "Lo siento, mi motor de inteligencia artificial está experimentando problemas técnicos."
    finally:
        db.close()
