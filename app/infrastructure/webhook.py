from fastapi import APIRouter, Form, Request, Response
from app.infrastructure.bot_logic import procesar_mensaje
from app.infrastructure.twilio_service import generar_respuesta_twilio

router = APIRouter()

@router.post("/whatsapp")
async def webhook_whatsapp(
    From: str = Form(...),
    Body: str = Form(...)
):
    """
    Endpoint principal (Webhook) donde Twilio envía los mensajes entrantes de WhatsApp.
    Recibe los datos como Form (application/x-www-form-urlencoded).
    """
    # 1. Extraer el número del remitente y el mensaje
    # Twilio envía el número en el formato "whatsapp:+1234567890"
    numero_remitente = From.replace("whatsapp:", "")
    mensaje_texto = Body

    # 2. Procesar la lógica del negocio (Máquina de estados y delay humano)
    # Aquí es donde ocurre la magia: determinamos qué responder
    respuesta_texto = await procesar_mensaje(numero_remitente, mensaje_texto)

    # 3. Formatear la respuesta para que Twilio la entienda
    # Twilio espera un XML (TwiML) en la respuesta HTTP
    xml_response = generar_respuesta_twilio(respuesta_texto)

    # 4. Devolver la respuesta con el Content-Type correcto (application/xml)
    return Response(content=xml_response, media_type="application/xml")
