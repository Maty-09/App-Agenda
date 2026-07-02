# PoC Bot de WhatsApp con FastAPI y Twilio

Este proyecto es una Prueba de Concepto (PoC) para un bot de agendamiento por WhatsApp. 
Utiliza FastAPI, Python 3.10+ y la API de Twilio Sandbox (TwiML).

## Estructura del Proyecto

- `main.py`: Punto de entrada de la aplicación FastAPI.
- `routes/webhook.py`: Controlador que recibe los POST de Twilio.
- `services/twilio_service.py`: Adaptador que aísla la lógica específica de Twilio (TwiML).
- `services/bot_logic.py`: Máquina de estados en memoria que maneja el flujo de la conversación.
- `utils/humanizer.py`: Utilidad para simular el tipeo humano (delay).

## Requisitos Previos

- Python 3.10 o superior
- Una cuenta en Twilio (para usar el Sandbox de WhatsApp)
- Ngrok instalado para exponer el puerto local a internet.

## Instalación y Ejecución

1.  **Clonar o descargar el proyecto**.
2.  **Crear un entorno virtual** (opcional pero recomendado):
    ```bash
    python -m venv venv
    venv\Scripts\activate  # En Windows
    ```
3.  **Instalar las dependencias**:
    ```bash
    pip install -r requirements.txt
    ```
4.  **Levantar el servidor local**:
    ```bash
    uvicorn main:app --reload --port 8000
    ```
    El servidor estará corriendo en `http://127.0.0.1:8000`.

## Conexión con Twilio usando Ngrok

Para que Twilio pueda enviar mensajes a tu entorno local, necesitas exponer tu puerto 8000 a internet.

1.  **Abre una nueva terminal** y ejecuta Ngrok:
    ```bash
    ngrok http 8000
    ```
2.  Copia la URL segura (HTTPS) que te proporciona Ngrok (ejemplo: `https://xxxx-xx-xx.ngrok-free.app`).
3.  Ve a la consola de Twilio: **Messaging > Try it out > Send a WhatsApp message**.
4.  Configura el Sandbox uniéndote con el código proporcionado.
5.  Ve a la pestaña **Sandbox settings**.
6.  En el campo **"WHEN A MESSAGE COMES IN"**, pega la URL de Ngrok seguida de la ruta del webhook:
    ```
    https://xxxx-xx-xx.ngrok-free.app/api/whatsapp
    ```
7.  Asegúrate de que el método sea `HTTP POST` y guarda los cambios.

## Probar el Bot

Desde tu WhatsApp, envía un mensaje al número del Sandbox de Twilio (por ejemplo: "Hola"). Deberías experimentar el bot respondiendo con el tiempo de tipeo simulado y guiándote por el flujo de reservas.
