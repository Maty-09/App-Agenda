from fastapi import APIRouter, Depends, HTTPException,Request, Query, Form
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal , get_db
from app.infrastructure.email_utils import (
    enviar_confirmacion_agendamiento,
    enviar_aviso_accion_al_dueno,
    enviar_solicitud_confirmacion,
    validar_token_confirmacion,
    enviar_aviso_recibido_cliente
)
from app.core.generar_utm import generar_utm 
from app.core import models
from app.core.models import get_now_chile
from app.domain_agenda import horarios
from app.core.booking_origin import ORIGEN_AGENDA_WEB, normalizar_origen_web
from app.core.auth_deps import CurrentUser, verificar_login_opcional
from app.infrastructure.notifications import enviar_notificacion
from sqlalchemy import func
import html
import math
import json
import pytz
import logging
from typing import List

logger = logging.getLogger(__name__)


# pruebas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()


def equipos_configurados(tenant) -> List[str]:
    try:
        equipos = json.loads(tenant.config_json or "{}").get("negocio", {}).get("equipos", [])
        return [str(equipo).strip() for equipo in equipos if str(equipo).strip()] or ["Agenda principal"]
    except (TypeError, ValueError, json.JSONDecodeError):
        return ["Agenda principal"]

import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _booking_path(tenant_id: str) -> str:
    return f"/cliente/{tenant_id}/agendar_web" if tenant_id != "default" else "/cliente/agendar_web"


def _config_tenant(tenant) -> dict:
    try:
        return json.loads(tenant.config_json or "{}") if tenant else {}
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _duracion_config_horas(config: dict) -> float:
    """Duración estándar del servicio según la configuración del negocio (en horas).

    Puede ser fraccionaria (p. ej. 0.5 = 30 minutos).
    """
    try:
        minutos = int(config.get("negocio", {}).get("duracion_minutos", 120))
    except (TypeError, ValueError):
        minutos = 120
    return max(15, min(480, minutos)) / 60


def _formato_duracion(horas: float) -> str:
    """Serializa la duración para el formulario sin decimales innecesarios."""
    return str(int(horas)) if float(horas).is_integer() else f"{horas:g}"


def _render_formulario(request: Request, tenant, tenant_id: str, status_code: int = 200, **extra):
    """Renderiza agendar.html con el contexto mínimo que la plantilla necesita.

    Las respuestas de error deben incluir los datos del negocio; si no, la
    plantilla falla al leer `negocio` y el cliente ve un error 500.
    """
    config = _config_tenant(tenant)
    reglas = config.get("reglas_negocio", {})
    try:
        dias_anticipacion = max(1, min(int(reglas.get("dias_anticipacion", 30)), 365))
    except (TypeError, ValueError):
        dias_anticipacion = 30
    contexto = {
        "request": request,
        "tenant_id": tenant_id,
        "negocio": config.get("negocio", {}),
        "nombre_empresa": getattr(tenant, "nombre_empresa", None),
        "dias_anticipacion": dias_anticipacion,
        "dias_habiles_config": sorted(horarios.dias_abiertos(config)),
        "booking_path": _booking_path(tenant_id),
        "horas_disponibles": [],
        "campos_dinamicos": [],
        "fecha_seleccionada": None,
        "hora_confirmada": None,
    }
    contexto.update(extra)
    return templates.TemplateResponse("agendar.html", contexto, status_code=status_code)


@router.get("/agendar_web", response_class=HTMLResponse)
@router.get("/{tenant_id}/agendar_web", response_class=HTMLResponse)
def agendar_web(
    request: Request,
    tipo: str = Query(None),
    subtipo: str = Query(None),
    fecha: str = Query(None),
    hora: str = Query(None),
    duracion_horas: float = Query(None),
    db: Session = Depends(get_db),
    tenant_id: str = "default"
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    try:
        config_negocio = json.loads(tenant.config_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        config_negocio = {}
    reglas_negocio = config_negocio.get("reglas_negocio", {})
    dias_anticipacion = max(1, min(int(reglas_negocio.get("dias_anticipacion", 30)), 365))
    dias_habiles_config = sorted(horarios.dias_abiertos(config_negocio))
    # 1. NORMALIZACIÓN Y VALIDACIÓN INICIAL
    tipo = tipo.lower().strip() if tipo else "domicilio_taller"
    subtipo = subtipo.lower().strip() if subtipo else "local"
    subtipo_db = "taller" if subtipo == "local" else subtipo

    if tipo not in ["domicilio_taller"]:
        return RedirectResponse(url=f"{_booking_path(tenant_id)}?tipo=domicilio_taller", status_code=302)

    # 2. OBTENER CAMPOS DINÁMICOS (Lo que configuraste en el Admin)
    # Filtramos por el subtipo para que si es Local salgan unos y si es Domicilio otros
    campos_dinamicos = []
    # Una cuenta nueva no hereda nunca el formulario de la agenda base. Sólo se
    # muestran los campos que su administrador eligió al completar el onboarding.
    if not config_negocio.get("onboarding_requerido"):
        campos_dinamicos = db.query(models.CampoFormulario).filter(
            models.CampoFormulario.tenant_id == tenant_id,
            models.CampoFormulario.subtipo_servicio == subtipo_db,
            models.CampoFormulario.activo == True
        ).order_by(models.CampoFormulario.orden.asc()).all()

    # 3. LÓGICA DE CALENDARIO Y HORAS (Tu lógica actual)
    # Sólo el modo emergencia (dueño) puede elegir otra duración; el cliente
    # siempre agenda con la duración configurada para el negocio.
    if duracion_horas is None or request.query_params.get("modo") != "emergencia":
        duracion_horas = _duracion_config_horas(config_negocio)
    duracion_horas = max(0.25, min(8, duracion_horas))

    horas_disponibles = []
    mensaje_error = None
    fecha_seleccionada = fecha
    hora_termino = None

    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            horas_disponibles = obtener_horas_disponibles(tipo, fecha_obj, duracion_horas, db, tenant_id)
            if not horas_disponibles:
                mensaje_error = "No quedan horarios disponibles para esa fecha. Elige otro día."
                fecha_seleccionada = None
                hora = None
            elif hora and hora not in horas_disponibles and request.query_params.get("modo") != "emergencia":
                mensaje_error = "Ese horario ya no está disponible. Elige otro."
                hora = None
            if hora:
                inicio = datetime.combine(fecha_obj, datetime.strptime(hora, "%H:%M").time())
                hora_termino = (inicio + timedelta(hours=duracion_horas)).strftime("%H:%M")
        except ValueError:
            mensaje_error = "La fecha u hora seleccionada no es válida. Inténtalo nuevamente."
            fecha_seleccionada = None
            hora = None

    embed_mode = request.query_params.get("norem_embed") == "1"
    embed_site = normalizar_origen_web(request.query_params.get("norem_site")) if embed_mode else None

    # 4. RENDER FINAL (Un solo return al final de la función)
    return templates.TemplateResponse("agendar.html", {
        "request": request,
        "tenant_id": tenant_id,
        "tipo": tipo,
        "subtipo": subtipo,
        "fecha_seleccionada": fecha_seleccionada,
        "hora_confirmada": hora,
        "duracion_horas": _formato_duracion(duracion_horas),
        "horas_disponibles": horas_disponibles,
        "hora_termino": hora_termino,
        "mensaje_error": mensaje_error,
        "campos_dinamicos": campos_dinamicos, # <--- ESTO ES LO QUE USA EL HTML
        "negocio": config_negocio.get("negocio", {}),
        "nombre_empresa": tenant.nombre_empresa,
        "dias_anticipacion": dias_anticipacion,
        "dias_habiles_config": dias_habiles_config,
        "embed_mode": embed_mode,
        "embed_site": embed_site,
        "utm_source": "whatsapp",
        "utm_campaign": f"{tipo}_{subtipo}",
        "booking_path": _booking_path(tenant_id),
    })

def dias_habiles_tenant(db: Session, tenant_id: str) -> set:
    """Días que el negocio atiende (0=lunes … 6=domingo), según su horario semanal."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    return horarios.dias_abiertos(_config_tenant(tenant))

@router.post("/agendar_web", response_class=HTMLResponse)
@router.post("/{tenant_id}/agendar_web", response_class=HTMLResponse)
async def recibir_formulario(
    request: Request,
    db: Session = Depends(get_db),
    tenant_id: str = "default",
    current_user: CurrentUser | None = Depends(verificar_login_opcional),
):
    form_data = {}
    is_web_embed = False
    embed_site = None
    tenant = None
    try:
        form_data = await request.form()
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).with_for_update().first()
        if not tenant or tenant.estado_suscripcion == "cancelada":
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        is_web_embed = form_data.get("norem_embed") == "1"
        embed_site = normalizar_origen_web(form_data.get("norem_site")) if is_web_embed else None
        
        tipo_servicio = form_data.get("tipo_servicio")
        subtipo = form_data.get("subtipo")
        subtipo = subtipo.lower().strip() if subtipo else "local"
        subtipo_db = "taller" if subtipo == "local" else subtipo
        fecha = form_data.get("fecha")
        hora = form_data.get("hora")
        
        # --- 1. DETECTAR MODO EMERGENCIA (DUEÑO) ---
        # Lo detectamos si viene en la URL o en un campo oculto del formulario
        solicita_emergencia = (
            request.query_params.get("modo") == "emergencia"
            or form_data.get("modo_emergencia") == "true"
            or form_data.get("modo") == "emergencia"
        )
        es_dueno = bool(
            solicita_emergencia
            and current_user
            and current_user.tenant_id == tenant_id
            and current_user.rol in {"admin", "admin_empresa", "superadmin"}
        )

        nota_interna = form_data.get("nota_interna", "")

        try:
            fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="Selecciona una fecha y hora válidas.")
        fecha_cliente = pytz.timezone('America/Santiago').localize(fecha_inicio)

        # --- 2. VALIDACIONES DE FECHA (SE SALTAN SI ES DUEÑO) ---
        if not es_dueno:
            # Regla A: 48h hábiles. Por ahora no bloquea la reserva: sólo deja
            # una marca en la nota interna para que el negocio la identifique.
            if fecha_cliente < obtener_fecha_minima_habil(db, tenant_id):
                nota_interna = (nota_interna or "") + " | EXCEPCION_48H"

            # Regla B: Verificar si el día está bloqueado manualmente
            dia_bloqueado = db.query(models.DiaBloqueado).filter(
                models.DiaBloqueado.tenant_id == tenant_id,
                models.DiaBloqueado.fecha == fecha_inicio.date(),
            ).first()
            if dia_bloqueado:
                raise HTTPException(status_code=409, detail="Este día el local se encuentra cerrado. Por favor selecciona otra fecha.")

        equipo_asignado = None

        # 3. MAPEO DE CAMPOS DINÁMICOS
        respuestas = {}
        campos_db = db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == tenant_id).all()
        
        # Crear mapa de mapeos de nombres técnicos a claves normalizadas
        mapeo_nombres = {
            "rut": ["rut", "run"],
            "correo": ["correo", "email", "mail", "e-mail"],
            "nombre": ["nombre"],
            "apellido": ["apellido"],
            "telefono": ["telefono", "phone", "celular"],
            "marca": ["marca"],
            "modelo": ["modelo"],
            "patente": ["patente", "patent"],
            "kilometraje": ["kilometraje", "kilometros"],
            "direccion": ["direccion", "dirección", "address"],
            "tipo_vivienda": ["tipo_vivienda", "tipo vivienda"]
        }
        
        for c in campos_db:
            valor = form_data.get(f"dinamico_{c.id}")
            if valor:
                nombre_tecnico_normalizado = (c.nombre_tecnico or c.label or "campo").lower().strip()
                
                # Buscar la clave normalizada correcta
                clave_final = None
                for clave_standard, aliases in mapeo_nombres.items():
                    if nombre_tecnico_normalizado in aliases:
                        clave_final = clave_standard
                        break
                
                # Si no encontró mapeo, usar el nombre técnico tal cual
                if not clave_final:
                    clave_final = nombre_tecnico_normalizado
                
                respuestas[clave_final] = valor

        # 2. ASIGNACIÓN DE VARIABLES (Mejorado con fallbacks)
        rut = respuestas.get("rut") or f"WEB-{tenant_id}-{int(datetime.utcnow().timestamp())}"
        nombre = respuestas.get("nombre") or "Cliente web"
        apellido = respuestas.get("apellido") or ""
        correo = respuestas.get("correo") or "sin-correo@norem.local"
        telefono = respuestas.get("telefono") or "Sin teléfono"
        marca = respuestas.get("marca") or "N/A"
        modelo = respuestas.get("modelo") or "N/A"
        patente = (respuestas.get("patente") or "S/P").upper()
        kilometraje = respuestas.get("kilometraje")
        direccion = respuestas.get("direccion") or form_data.get("direccion")
        tipo_vivienda = respuestas.get("tipo_vivienda") or form_data.get("tipo_vivienda") or "No especificado"

        # 3. VALIDACIÓN DE CAMPOS OBLIGATORIOS
        if correo == "sin-correo@norem.local":
            raise HTTPException(
                status_code=422,
                detail="Necesitamos tu correo electrónico para enviarte la confirmación. Si el formulario no lo pide, contacta al negocio.",
            )

        # 4. LÓGICA DE DURACIÓN
        # El cliente no puede alterar la duración desde el formulario: se usa
        # la configurada por el negocio. Sólo el dueño (modo emergencia) la elige.
        duracion_horas = _duracion_config_horas(_config_tenant(tenant))
        if es_dueno:
            try:
                duracion_horas = float(form_data.get("duracion_horas") or duracion_horas)
            except (TypeError, ValueError):
                pass

        if not 0.25 <= duracion_horas <= 8:
            raise HTTPException(status_code=422, detail="La duración solicitada no es válida")

        fecha_termino = fecha_inicio + timedelta(hours=duracion_horas)

        if not es_dueno and not verificar_disponibilidad(
            db, tipo_servicio, fecha_inicio, duracion_horas, tenant_id
        ):
            raise HTTPException(status_code=409, detail="El horario seleccionado ya no está disponible. Elige otro horario.")
        # --- 5. LÓGICA DE ASIGNACIÓN AUTOMÁTICA DE EQUIPO ---
        # Definimos los equipos por tipo de servicio
        equipos_posibles = equipos_configurados(tenant)
        
        equipo_asignado = None

        for eq in equipos_posibles:
            # ¿Este equipo específico está ocupado a esta hora?
            ocupado = db.query(models.Agendamiento).filter(
                models.Agendamiento.tenant_id == tenant_id,
                models.Agendamiento.equipo == eq,
                models.Agendamiento.fecha_inicio < fecha_termino,
                models.Agendamiento.fecha_termino > fecha_inicio,
                models.Agendamiento.estado != "cancelado"
            ).first()
            
            if not ocupado:
                equipo_asignado = eq
                break # Asignamos al primero que esté libre y paramos
        
        # Si no hay equipo libre pero es el DUEÑO, forzamos el primero de la lista (Sobrecupo)
        if not equipo_asignado and es_dueno:
            equipo_asignado = equipos_posibles[0]

        if not equipo_asignado:
            raise HTTPException(status_code=409, detail="No hay un equipo disponible en ese horario. Elige otro horario.")

        # 6. LÓGICA CRM: CREAR O BUSCAR CLIENTE
        cliente = db.query(models.Cliente).filter(
            models.Cliente.rut == rut,
            models.Cliente.tenant_id == tenant_id
        ).first()

        if not cliente:
            cliente = models.Cliente(
                tenant_id=tenant_id,
                rut=rut,
                nombre=nombre,
                apellido=apellido,
                telefono=telefono,
                correo=correo,
                etiquetas=json.dumps(["Web"])
            )
            db.add(cliente)
            db.flush()
        else:
            # Actualizar datos de contacto si cambiaron
            if telefono != cliente.telefono or correo != cliente.correo:
                cliente.telefono = telefono
                cliente.correo = correo
                db.flush()

        # 7. GUARDAR EN BASE DE DATOS
        nueva = models.Agendamiento(
            tenant_id=tenant_id,
            cliente_id=cliente.id,
            rut=rut, 
            nombre=nombre, 
            apellido=apellido, 
            correo=correo, 
            telefono=telefono,
            tipo_vivienda=tipo_vivienda, 
            direccion=direccion,
            marca=marca, 
            modelo=modelo, 
            patente=patente, 
            kilometraje=kilometraje,
            tipo_servicio=tipo_servicio, 
            subtipo=subtipo_db, 
            equipo=equipo_asignado,
            fecha_inicio=fecha_inicio, 
            fecha_termino=fecha_termino, 
            # Columna legacy entera; las fechas guardan la duración real.
            duracion_horas=max(1, math.ceil(duracion_horas)),
            nota_interna = nota_interna,
            utm_source_real=ORIGEN_AGENDA_WEB if is_web_embed else None,
            utm_link=embed_site,
            estado="pendiente"
        )
        db.add(nueva)
        db.flush()
        
        # 8. REGISTRAR TIMELINE EVENT
        evento = models.TimelineEvent(
            tenant_id=tenant_id,
            cliente_id=cliente.id,
            tipo_evento="RESERVA",
            metadata_json=json.dumps({
                "agendamiento_id": nueva.id,
                "fecha": str(nueva.fecha_inicio),
                "origen": ORIGEN_AGENDA_WEB if is_web_embed else "Web",
                "sitio": embed_site,
            })
        )
        db.add(evento)
        
        db.commit()
        db.refresh(nueva)
        
    # 7. ENVÍO DE AVISO INICIAL
        try:
        # 1. ESTO ES LO ÚNICO QUE LLEGA AL AGENDAR
            enviar_notificacion(nueva.id, "creada")
            
        except Exception:
            logger.error("booking_notification_failed tenant_id=%s", tenant_id)

        return _render_formulario(
            request, tenant, tenant_id,
            success=True,
            correo_cliente=correo,
            fecha_reserva=fecha_inicio.strftime("%d/%m/%Y"),
            hora_reserva=fecha_inicio.strftime("%H:%M"),
            tipo=tipo_servicio,
            subtipo=subtipo,
            embed_mode=is_web_embed,
            embed_site=embed_site,
        )

    except HTTPException as exc:
        db.rollback()
        return _render_formulario(
            request, tenant, tenant_id,
            status_code=exc.status_code,
            mensaje_error=exc.detail,
            tipo=form_data.get("tipo_servicio") or "domicilio_taller",
            subtipo=form_data.get("subtipo") or "local",
            embed_mode=is_web_embed,
            embed_site=embed_site,
        )
    except Exception:
        db.rollback()
        logger.exception("booking_submission_failed tenant_id=%s", tenant_id)
        return _render_formulario(
            request, tenant, tenant_id,
            status_code=500,
            mensaje_error="No se pudo completar la reserva. Revisa los datos e inténtalo nuevamente.",
            tipo=form_data.get("tipo_servicio") or "domicilio_taller",
            subtipo=form_data.get("subtipo") or "local",
            embed_mode=is_web_embed,
            embed_site=embed_site,
        )

def calcular_fin_especializado(inicio: datetime, duracion: int) -> datetime:
    horas_asignadas = 0
    actual = inicio

    while horas_asignadas < duracion:
        # Si justo llegamos a las 12:00, saltamos directo a las 13:00s
        if actual.hour == 12 and actual.minute == 0:
            actual = actual.replace(hour=13, minute=0)
        else:
            actual += timedelta(hours=1)
            horas_asignadas += 1

    return actual

Recursos = {
    "domicilio_taller": ["Equipo Cristhian", "Equipo Samuel", "Equipo Movil"], # 3 equipos para este tipo
    "especializado": ["Equipo Cristhian", "Equipo Samuel", "Equipo Movil"],
}

def _reglas_agenda(tenant) -> dict:
    reglas = _config_tenant(tenant).get("reglas_negocio", {})
    return reglas if isinstance(reglas, dict) else {}


def _primer_inicio_permitido(tenant) -> datetime:
    """Hora actual más la anticipación mínima que exige el negocio (0 por defecto)."""
    try:
        horas = max(0, min(int(_reglas_agenda(tenant).get("horas_minimas_anticipacion", 0)), 720))
    except (TypeError, ValueError):
        horas = 0
    return get_now_chile().replace(tzinfo=None) + timedelta(hours=horas)


def _bloques_del_dia(tenant, dia_semana, duracion_horas):
    """Horas de inicio que el negocio ofrece ese día según su horario semanal."""
    return horarios.inicios_del_dia(_config_tenant(tenant), dia_semana, duracion_horas * 60)


def obtener_horas_disponibles(tipo_servicio, fecha, duracion_horas, db, tenant_id="default"):
    """Calcula disponibilidad con reglas del tenant y consultas acotadas por día."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant or fecha.weekday() not in dias_habiles_tenant(db, tenant_id):
        return []
    if horarios.cerrado_por_feriado(_config_tenant(tenant), fecha) or db.query(models.DiaBloqueado.id).filter(
        models.DiaBloqueado.tenant_id == tenant_id, models.DiaBloqueado.fecha == fecha
    ).first():
        return []

    bloques_dia = _bloques_del_dia(tenant, fecha.weekday(), duracion_horas)
    candidatos = []
    primer_inicio = _primer_inicio_permitido(tenant)
    for bloque in bloques_dia:
        try:
            inicio = datetime.combine(fecha, datetime.strptime(bloque, "%H:%M").time())
        except ValueError:
            continue
        if inicio < primer_inicio:
            continue
        termino = calcular_fin_especializado(inicio, duracion_horas) if tipo_servicio == "especializado" else inicio + timedelta(hours=duracion_horas)
        candidatos.append((bloque, inicio, termino))
    if not candidatos:
        return []

    inicio_rango = min(inicio for _, inicio, _ in candidatos)
    fin_rango = max(termino for _, _, termino in candidatos)
    reservas = db.query(models.Agendamiento.fecha_inicio, models.Agendamiento.fecha_termino).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio < fin_rango,
        models.Agendamiento.fecha_termino > inicio_rango,
        models.Agendamiento.estado != "cancelado",
    ).all()
    capacidad = max(1, len(equipos_configurados(tenant)))
    return [
        bloque for bloque, inicio, termino in candidatos
        if sum(reserva_inicio < termino and reserva_fin > inicio for reserva_inicio, reserva_fin in reservas) < capacidad
    ]


def verificar_disponibilidad(db: Session, tipo_servicio: str, inicio: datetime, duracion_horas: int, tenant_id: str = "default") -> bool:

    inicio_naive = inicio.replace(tzinfo=None)
    if inicio_naive < get_now_chile().replace(tzinfo=None):
        return False

    # 1. NUEVO: Chequear si el día está bloqueado por administración
    dia_bloqueado = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.tenant_id == tenant_id, models.DiaBloqueado.fecha == inicio.date()).first()
    if dia_bloqueado:
        return False  # Si el día está bloqueado, no hay disponibilidad para nadie

    if inicio.weekday() not in dias_habiles_tenant(db, tenant_id):
        return False

    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if horarios.cerrado_por_feriado(_config_tenant(tenant), inicio.date()):
        return False

    tz_chile = pytz.timezone("America/Santiago")
    
    if inicio.tzinfo is None:
        inicio = tz_chile.localize(inicio)

   # 1. Calcular fin
    if tipo_servicio == "especializado":
        fin = calcular_fin_especializado(inicio, duracion_horas)
    else:
        fin = inicio + timedelta(hours=duracion_horas)

    # Ahora sí podemos sacar los tiempos
    h_inicio = inicio.time()
    h_fin = fin.time()
    
    # 5. VALIDACIÓN DE BLOQUES HORARIOS DINÁMICOS
    dia_semana = inicio.weekday() 
    hora_str = inicio.strftime("%H:%M")

    bloques_validos = _bloques_del_dia(tenant, dia_semana, duracion_horas)

    # Verificamos si la hora requerida está dentro de los bloques permitidos para ese día
    if hora_str not in bloques_validos:
        return False

    # Regla propia del negocio: anticipación mínima.
    if inicio.replace(tzinfo=None) < _primer_inicio_permitido(tenant):
        return False
        
    # 6. Validar traslapes en la DB
    # Contamos cuántos equipos están ocupados en este bloque
    inicio_db = inicio.replace(tzinfo=None)
    fin_db = fin.replace(tzinfo=None)
    agendados_en_bloque = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio < fin_db,
        models.Agendamiento.fecha_termino > inicio_db,
        models.Agendamiento.estado != "cancelado"
    ).count()

    limite_equipos = len(equipos_configurados(tenant))
    
    return agendados_en_bloque < limite_equipos


def _cita_desde_token(token: str, db: Session):
    parsed = validar_token_confirmacion(token)
    if not parsed:
        return None
    booking_id, tenant_id = parsed
    return db.query(models.Agendamiento).filter(
        models.Agendamiento.id == booking_id,
        models.Agendamiento.tenant_id == tenant_id,
    ).first()


@router.get("/confirmar/{token}")
async def confirmar_cita_form(token: str, db: Session = Depends(get_db)):
    cita = _cita_desde_token(token, db)
    if not cita or cita.estado == "cancelado":
        return HTMLResponse("Enlace inválido o vencido.", status_code=404)
    if cita.estado == "confirmado":
        return HTMLResponse("Tu cita ya está confirmada.")
    safe_token = html.escape(token, quote=True)
    return HTMLResponse(f"""
        <html><body style="font-family:sans-serif;text-align:center;padding:48px 16px;color:#172033">
        <h2>Confirma tu cita</h2><p>Presiona el botón para confirmar la reserva.</p>
        <form method="post" action="/cliente/confirmar/{safe_token}">
          <button type="submit" style="padding:12px 22px;background:#1557c0;color:white;border:0;border-radius:8px;font-weight:bold">Confirmar mi cita</button>
        </form></body></html>
    """)


@router.post("/confirmar/{token}")
async def confirmar_cita_endpoint(token: str, db: Session = Depends(get_db)):
    agendamiento = _cita_desde_token(token, db)
    if not agendamiento or agendamiento.estado == "cancelado":
        return HTMLResponse("Enlace inválido o vencido.", status_code=404)

    if agendamiento.estado != "confirmado":
        agendamiento.estado = "confirmado"
        db.commit()
        enviar_confirmacion_agendamiento(agendamiento, "Confirmación Exitosa")
        enviar_aviso_accion_al_dueno(agendamiento, "ACEPTADA ✅")

    return HTMLResponse("""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: sans-serif; text-align: center; padding-top: 50px; background: #f4f7f6; color: #1e293b; }
                    .loader { border: 4px solid #f3f3f3; border-top: 4px solid #10b981; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 20px auto; }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <h2 style="color:#10b981;">✅ ¡Listo!</h2>
                <p>Tu cita ha sido confirmada.</p>
                <p>Revisa tu correo ahora para ver el calendario.</p>
                <script>
                    // Intentamos cerrar la pestaña tras 2 segundos
                    setTimeout(function(){ 
                        window.close(); 
                        // En algunos móviles window.close() no funciona si no fue abierto por JS,
                        // por lo que el mensaje de arriba es el respaldo perfecto.
                    }, 2500);
                </script>
            </body>
        </html>
    """)

def obtener_fecha_minima_habil(db: Session, tenant_id: str):
    """Fecha/hora a partir de la cual se cumplen 48 horas en días hábiles."""
    tz_chile = pytz.timezone('America/Santiago')
    fecha_chequeo = datetime.now(tz_chile)
    dias_habiles = dias_habiles_tenant(db, tenant_id)  # una sola consulta
    if not dias_habiles:
        # Sin días hábiles configurados el bucle nunca terminaría.
        return fecha_chequeo
    horas_contadas = 0
    while horas_contadas < 48:
        fecha_chequeo += timedelta(hours=1)
        if fecha_chequeo.weekday() in dias_habiles:
            horas_contadas += 1
    return fecha_chequeo


@router.get("/api/horas-disponibles")
def api_horas(
    fecha: str,
    tipo: str = "domicilio_taller",
    duracion: float | None = None,
    tenant_id: str = "default",
    db: Session = Depends(get_db)
):
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        return {"horas": []}
    if duracion is None:
        # Por defecto, la duración que configuró el negocio (puede ser en minutos).
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
        duracion = _duracion_config_horas(_config_tenant(tenant))
    duracion = max(0.25, min(8, duracion))
    return {"horas": obtener_horas_disponibles(tipo, fecha_obj, duracion, db, tenant_id)}
