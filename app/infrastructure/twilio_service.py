from twilio.twiml.messaging_response import MessagingResponse

def generar_respuesta_twilio(mensaje: str) -> str:
    """
    Recibe un string con el mensaje a enviar y genera el XML (TwiML)
    que Twilio espera como respuesta al webhook.
    
    Aísla la dependencia de Twilio aquí para que sea fácil cambiar
    a meta_service.py en el futuro.
    """
    response = MessagingResponse()
    response.message(mensaje)
    return str(response)
