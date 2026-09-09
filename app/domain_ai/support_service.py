"""Asistente de soporte Norem: respuestas seguras y lenguaje natural opcional."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any

import requests
from sqlalchemy.orm import Session

from app.core import models


ESCALATION_MESSAGE = (
    "Para revisar esto con seguridad, necesito escalarlo a soporte. "
    "Comparte el correo de tu cuenta y la hora aproximada en que ocurrió el problema; "
    "no envíes contraseñas, códigos ni datos de tarjeta."
)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _business_config(tenant: models.Tenant) -> dict[str, Any]:
    try:
        config = json.loads(tenant.config_json or "{}")
        return config if isinstance(config, dict) else {}
    except json.JSONDecodeError:
        return {}


def _agenda_context(db: Session, tenant_id: str) -> str:
    """Entrega solo un resumen operativo; nunca expone datos personales en el prompt."""
    now = models.get_now_chile()
    tomorrow = now.date() + timedelta(days=1)
    today_count = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio >= datetime.combine(now.date(), datetime.min.time()),
        models.Agendamiento.fecha_inicio < datetime.combine(tomorrow, datetime.min.time()),
        models.Agendamiento.estado != "cancelado",
    ).count()
    next_booking = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio >= now,
        models.Agendamiento.estado != "cancelado",
    ).order_by(models.Agendamiento.fecha_inicio.asc()).first()
    if next_booking:
        next_text = next_booking.fecha_inicio.strftime("%d/%m a las %H:%M")
    else:
        next_text = "no hay una próxima reserva registrada"
    return f"Hoy hay {today_count} reserva(s) activa(s). La próxima reserva: {next_text}."


def _guided_reply(message: str, tenant: models.Tenant, db: Session) -> str:
    text = _normalize(message)
    business_name = tenant.nombre_empresa or "tu negocio"

    if not text:
        return "Cuéntame qué quieres hacer en Norem y te guío paso a paso."

    if any(word in text for word in ("hola", "buenas", "como estas", "qué puedes hacer", "que puedes hacer")):
        return (
            f"¡Hola! Soy el asistente de Norem para {business_name}. "
            "Puedo ayudarte con agenda, clientes, tareas, configuración, correos e integración web. ¿Qué necesitas hacer?"
        )

    if any(word in text for word in ("contraseña", "contrasena", "recuperar acceso", "no puedo entrar", "iniciar sesión", "iniciar sesion")):
        return (
            "En la pantalla de inicio de sesión selecciona ‘Olvidé mi contraseña’, escribe el correo de tu cuenta "
            "y abre el enlace que recibirás. Revisa spam y promociones. "
            "No compartas tu contraseña ni el código de recuperación con nadie."
        )

    if any(word in text for word in ("correo", "email", "recordatorio", "confirmación", "confirmacion", "no llegó", "no llego")):
        return (
            "Primero revisa spam y promociones, confirma que el correo del cliente esté correcto y espera unos minutos. "
            f"Si el mensaje no llega después de eso, {ESCALATION_MESSAGE}"
        )

    if any(word in text for word in ("api", "integrar", "integración", "integracion", "página web", "pagina web", "sitio web", "widget")):
        return (
            "Puedes integrar tu agenda en cualquier sitio web. Ve a Configuración y abre ‘Integración web / API pública’, "
            "escribe el dominio de tu página y selecciona ‘Activar API y generar acceso’. "
            "Luego copia los datos de integración o envíaselos a quien administra tu sitio."
        )

    if any(word in text for word in ("prueba", "suscripción", "suscripcion", "plan", "cobro", "mercado pago", "pago")):
        return (
            "Puedes revisar el estado de tu prueba o suscripción desde la sección Plan. "
            "Si ves un cobro o estado que no reconoces, no intentes modificarlo desde aquí. "
            + ESCALATION_MESSAGE
        )

    if any(word in text for word in ("bloquear", "cerrar día", "cerrar dia", "feriado")):
        return (
            "Para cerrar una fecha, entra a Configuración de agenda, selecciona el día y registra un motivo si lo necesitas. "
            "Antes de guardar, revisa si ya existen reservas: los clientes afectados deben recibir el aviso de cancelación o reagendamiento configurado por el negocio."
        )

    if any(word in text for word in ("horario", "disponibilidad", "no hay hora", "no aparecen horas", "hora disponible")):
        return (
            "Las horas disponibles dependen de los días y bloques horarios configurados, la duración del servicio, capacidad, días bloqueados, feriados y disponibilidad futura. "
            "En Configuración revisa esos valores. Si me dices la fecha y el servicio que estás revisando, te indico qué validar primero."
        )

    if any(word in text for word in ("agenda", "calendario", "reserva", "cita", "hoy", "mañana", "manana")):
        return (
            _agenda_context(db, tenant.id)
            + " Para ver el detalle, entra a Calendario y abre la reserva. Desde ahí puedes revisar la información registrada por el cliente."
        )

    if any(word in text for word in ("cliente", "historial", "ficha", "contacto")):
        return (
            "Entra a Clientes y usa la búsqueda por nombre, correo, teléfono o identificador disponible. "
            "Abre la ficha para revisar historial, notas y próximas acciones."
        )

    if any(word in text for word in ("tarea", "pendiente", "equipo", "responsable")):
        return (
            "En Tareas puedes crear un pendiente, asignar responsable, prioridad y fecha límite. "
            "Mantén su estado actualizado para que el dashboard refleje la operación real."
        )

    if any(word in text for word in ("formulario", "campo", "pregunta", "marca", "modelo")):
        return (
            "Los campos de la agenda son configurables. Ve a Configuración y edita las preguntas que verá el cliente al reservar. "
            "Solicita solo los datos que tu negocio necesita; Norem no debería mostrar campos que no hayas configurado."
        )

    if any(word in text for word in ("configurar", "configuración", "configuracion", "negocio", "cambiar")):
        return (
            "Desde Configuración puedes ajustar datos del negocio, días y horarios de atención, duración, capacidad, disponibilidad futura y formulario. "
            "Guarda los cambios y revisa que no afecten reservas ya existentes."
        )

    return (
        "Te puedo orientar sobre agenda, reservas, clientes, tareas, configuración, correos, acceso, plan e integración web. "
        "Cuéntame qué quieres lograr y, si aparece un mensaje de error, compárteme el texto exacto sin incluir contraseñas ni códigos."
    )


def _naturalize(message: str, guided_reply: str, tenant: models.Tenant) -> str | None:
    """Usa una IA externa solo para redactar; nunca le da capacidad de ejecutar acciones."""
    api_key = os.getenv("INCEPTION_API_KEY")
    if not api_key:
        return None

    system = (
        "Eres el asistente de soporte de Norem. Responde solo en español de Chile, con tono humano, cercano y profesional. "
        "Tu única fuente de hechos es la orientación aprobada. No inventes funciones, precios, estados ni pasos. "
        "No pidas contraseñas, códigos, claves API ni datos de pago. No confirmes cambios ni reservas. "
        "Redacta máximo 120 palabras, con pasos numerados solo si ayudan.\n\n"
        f"Orientación aprobada: {guided_reply}"
    )
    payload = {
        "model": "mercury-2",
        "temperature": 0.25,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
    }
    try:
        response = requests.post(
            "https://api.inceptionlabs.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=8,
        )
        if not response.ok:
            return None
        text = response.json()["choices"][0]["message"]["content"].strip()
        return text[:1200] or None
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None


def answer_support_question(message: str, tenant: models.Tenant, db: Session) -> dict[str, str]:
    """Responde en modo guiado y, si existe credencial, naturaliza la respuesta."""
    guided_reply = _guided_reply(message, tenant, db)
    natural_reply = _naturalize(message, guided_reply, tenant)
    return {
        "reply": natural_reply or guided_reply,
        "mode": "ai" if natural_reply else "guided",
    }
