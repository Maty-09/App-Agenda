from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sqlalchemy import func, text, or_
from app.core.database import SessionLocal
from app.core import models, schemas, mercadopago_utils
from app.core.booking_origin import ORIGEN_AGENDA_WEB
from typing import List, Optional, Tuple
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import json
from fastapi.templating import Jinja2Templates
import os
from starlette.status import HTTP_303_SEE_OTHER
from datetime import datetime, timedelta, time as dt_time, date as dt_date
import pytz
import sqlite3
import openpyxl
from io import BytesIO 
from app.infrastructure.email_utils import (
    enviar_confirmacion_agendamiento,
    enviar_correo_cancelacion,
    enviar_correo_cancelacion_por_bloqueo,
    enviar_correo_recuperacion_contrasena,
    enviar_aviso_inicio_prueba,
    enviar_aviso_nueva_suscripcion,
)
from app.domain_agenda.router_cliente import Recursos, calcular_fin_especializado, equipos_configurados
from app.domain_agenda import horarios
from urllib.parse import quote
from app.domain_team import crud_team
import os
from pathlib import Path
import logging
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=[str(BASE_DIR / "templates"), str(BASE_DIR / "app" / "templates")])
logger = logging.getLogger(__name__)

router = APIRouter()
SYSTEM_BASE_URL = os.getenv("SYSTEM_BASE_URL", "https://agenda.norem.cl").rstrip("/")


def _cookie_secure(request: Request) -> bool:
    """Exige cookies Secure en producción; permite HTTP en desarrollo local."""
    return os.getenv("VERCEL") == "1" or request.url.scheme == "https"


def _set_session_cookie(response: RedirectResponse, request: Request, token: str) -> None:
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        secure=_cookie_secure(request),
        samesite="lax",
        path="/",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


def _delete_session_cookie(response: RedirectResponse, request: Request) -> None:
    response.delete_cookie(
        "access_token", path="/", secure=_cookie_secure(request),
        httponly=True, samesite="lax",
    )


def _avisar_activacion_interna(db: Session, tenant: models.Tenant, origen: str) -> None:
    """Notifica al equipo cuando una cuenta pasa a estar activa."""
    administrador = db.query(models.Usuario).filter(
        models.Usuario.tenant_id == tenant.id,
        models.Usuario.rol == "admin",
    ).first()
    if administrador and not enviar_aviso_nueva_suscripcion(tenant, administrador, origen):
        logger.warning("subscription_activation_internal_notification_failed")


# =============================
#     DEPENDENCIA DB
# =============================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# =============================
#     SECURITY & JWT
# =============================
from fastapi import HTTPException, status
from app.core import models, security, stripe_utils
from app.core.auth_deps import CurrentUser, verificar_login
import stripe
import hashlib
import secrets
import re
import unicodedata

ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 dÃ­as


def verificar_superadmin(cred: CurrentUser) -> None:
    if cred.tenant_id != "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de SuperAdmin.")


# =============================
#     LOGIN / LOGOUT
# =============================

def _destino_post_login(destino: Optional[str]) -> Optional[str]:
    """Evita redirecciones externas desde enlaces enviados por correo."""
    if destino in {"/admin/suscripcion", "/admin/api-publica"}:
        return destino
    return None


@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request, next: Optional[str] = Query(None), next_url: Optional[str] = Query(None)):
    destino = _destino_post_login(next_url) or _destino_post_login(next)
    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "next_url": destino,
    })

@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next_url: str = Form(""),
    db: Session = Depends(get_db),
):
    destino_solicitado = _destino_post_login(next_url)
    usuario = db.query(models.Usuario).filter(models.Usuario.email == username).first()

    if not usuario or not security.verify_password(password, usuario.password_hash):
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Correo o contraseña incorrectos",
            "next_url": destino_solicitado,
        })

    tenant = db.query(models.Tenant).filter(models.Tenant.id == usuario.tenant_id).first()
    if not tenant or tenant.estado_suscripcion == "cancelada":
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Esta cuenta está desactivada. Contacta a Norem para reactivarla.",
            "next_url": destino_solicitado,
        }, status_code=403)

    usuario.ultima_conexion = models.get_now_chile()
    usuario.sesion_activa = True
    db.commit()

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=usuario.id,
        rol=usuario.rol,
        tenant_id=usuario.tenant_id,
        email=usuario.email,
        expires_delta=access_token_expires
    )

    tenant = db.query(models.Tenant).filter(models.Tenant.id == usuario.tenant_id).first()
    config_inicio = _leer_config_tenant(tenant) if tenant else {}
    if destino_solicitado:
        destino = destino_solicitado
    elif config_inicio.get("onboarding_requerido") or not config_inicio.get("configuracion_inicial_completa", True):
        destino = "/admin/configuracion-inicial"
    elif not config_inicio.get("onboarding_completo", True):
        destino = "/admin/onboarding"
    else:
        destino = "/admin/dashboard"
    response = RedirectResponse(url=destino, status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, request, access_token)
    return response


def _crear_slug_empresa(nombre_empresa: str) -> str:
    limpio = unicodedata.normalize("NFKD", nombre_empresa).encode("ascii", "ignore").decode("ascii").lower()
    limpio = re.sub(r"[^a-z0-9]+", "-", limpio).strip("-")
    return (limpio or "negocio")[:36]


@router.get("/prueba", response_class=HTMLResponse)
def prueba_form(request: Request):
    return templates.TemplateResponse("trial_signup.html", {"request": request})


@router.post("/prueba", response_class=HTMLResponse)
def iniciar_prueba(
    request: Request,
    nombre_empresa: str = Form(...),
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if len(password) < 8:
        return templates.TemplateResponse("trial_signup.html", {"request": request, "error": "La contraseña debe tener al menos 8 caracteres."})
    if db.query(models.Usuario).filter(models.Usuario.email == email).first():
        return templates.TemplateResponse("trial_signup.html", {"request": request, "error": "Ya existe una cuenta con este correo. Inicia sesión o recupera tu contraseña."})

    base_id = _crear_slug_empresa(nombre_empresa)
    tenant_id = f"{base_id}-{secrets.token_hex(3)}"
    ahora = models.get_now_chile()
    tenant = models.Tenant(
        id=tenant_id,
        nombre_empresa=nombre_empresa.strip(),
        plan_actual="Norem · Prueba",
        estado_suscripcion="prueba",
        trial_inicio=ahora,
        trial_fin=ahora + timedelta(days=14),
        config_json=json.dumps({"onboarding_requerido": True}),
    )
    usuario = models.Usuario(
        tenant_id=tenant_id,
        nombre=nombre.strip(),
        email=email,
        password_hash=security.get_password_hash(password),
        rol="admin",
        ultima_conexion=ahora,
        sesion_activa=True,
    )
    db.add(tenant)
    db.add(usuario)
    db.commit()
    # El alta quedó confirmada en la base antes de avisar al equipo interno.
    if not enviar_aviso_inicio_prueba(tenant, usuario):
        logger.warning("trial_start_internal_notification_failed")
    token = security.create_access_token(
        subject=usuario.id, rol=usuario.rol, tenant_id=tenant_id, email=usuario.email,
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    response = RedirectResponse(url="/admin/configuracion-inicial", status_code=status.HTTP_303_SEE_OTHER)
    _set_session_cookie(response, request, token)
    return response


_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _leer_config_tenant(tenant: models.Tenant) -> dict:
    try:
        return json.loads(tenant.config_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _campos_contacto_iniciales(db: Session, tenant_id: str, campos: List[str]) -> None:
    """Crea solamente los campos elegidos durante el onboarding."""
    etiquetas = {"nombre": "Nombre", "correo": "Correo electrónico", "telefono": "Teléfono", "rut": "Identificación/RUT"}
    for orden, nombre_tecnico in enumerate(campos, start=1):
        if nombre_tecnico not in etiquetas:
            continue
        existe = db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == tenant_id, models.CampoFormulario.nombre_tecnico == nombre_tecnico).first()
        if not existe:
            db.add(models.CampoFormulario(tenant_id=tenant_id, label=etiquetas[nombre_tecnico], nombre_tecnico=nombre_tecnico, tipo_campo="email" if nombre_tecnico == "correo" else "text", subtipo_servicio="taller", obligatorio=True, orden=orden))


@router.get("/configuracion-inicial", response_class=HTMLResponse)
def configuracion_inicial_norem(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    config = _leer_config_tenant(tenant)
    if config.get("configuracion_inicial_completa"):
        return RedirectResponse("/admin/onboarding" if not config.get("onboarding_completo") else "/admin/dashboard", status_code=303)
    return templates.TemplateResponse("admin_onboarding.html", {"request": request, "current_user": cred, "tenant": tenant, "config": config, "dias": _DIAS})


@router.post("/configuracion-inicial")
def guardar_configuracion_inicial(nombre_empresa: str = Form(...), giro: str = Form(...), servicio_principal: str = Form(...), duracion_minutos: int = Form(60), hora_inicio: str = Form("09:00"), hora_fin: str = Form("18:00"), dias_habiles: List[int] = Form([]), campos_cliente: List[str] = Form([]), db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    if cred.rol not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Sólo el administrador puede configurar el negocio.")
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    dias = sorted({dia for dia in dias_habiles if 0 <= dia <= 6}) or [0, 1, 2, 3, 4]
    inicio = hora_inicio if re.fullmatch(r"\d{2}:\d{2}", hora_inicio) else "09:00"
    fin = hora_fin if re.fullmatch(r"\d{2}:\d{2}", hora_fin) else "18:00"
    config = _leer_config_tenant(tenant)
    config.update({"configuracion_inicial_completa": True, "onboarding_completo": False, "onboarding_requerido": False, "negocio": {"giro": giro.strip(), "servicio_principal": servicio_principal.strip(), "duracion_minutos": max(15, min(duracion_minutos, 480))}, "reglas_negocio": {"dias_habiles": dias, "horario_semanal": {str(dia): ([[inicio, fin]] if dia in dias and inicio < fin else []) for dia in range(7)}}})
    tenant.nombre_empresa, tenant.config_json = nombre_empresa.strip(), json.dumps(config)
    _campos_contacto_iniciales(db, tenant.id, campos_cliente)
    db.commit()
    return RedirectResponse("/admin/onboarding", status_code=303)


@router.get("/onboarding", response_class=HTMLResponse)
def onboarding_norem(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    config = _leer_config_tenant(tenant)
    if not config.get("configuracion_inicial_completa"):
        return RedirectResponse("/admin/configuracion-inicial", status_code=303)
    if config.get("onboarding_completo"):
        return RedirectResponse("/admin/dashboard", status_code=303)
    return templates.TemplateResponse("admin_product_onboarding.html", {"request": request, "current_user": cred, "tenant": tenant, "config": config})


@router.post("/onboarding/finalizar")
def finalizar_onboarding(db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    config = _leer_config_tenant(tenant)
    config["onboarding_completo"] = True
    tenant.config_json = json.dumps(config)
    db.commit()
    return RedirectResponse("/admin/dashboard", status_code=303)


@router.get("/configuracion-negocio", response_class=HTMLResponse)
def configuracion_negocio(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    config_actual = _leer_config_tenant(tenant)
    if not config_actual.get("configuracion_inicial_completa", True):
        return RedirectResponse("/admin/configuracion-inicial", status_code=303)
    if not config_actual.get("onboarding_completo", True):
        return RedirectResponse("/admin/onboarding", status_code=303)
    base_url = os.getenv("SYSTEM_BASE_URL", "https://agenda.norem.cl").rstrip("/")
    return templates.TemplateResponse("admin_business_config.html", {"request": request, "current_user": cred, "tenant": tenant, "config": config_actual, "dias": _DIAS, "horario": horarios.horario_semanal_texto(config_actual), "agenda_url": f"{base_url}/cliente/{tenant.id}/agendar_web", "api_url": f"{base_url}/api/v1/public/{tenant.id}/agenda"})


@router.get("/integraciones", response_class=HTMLResponse)
def integraciones(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    return RedirectResponse("/admin/api-publica", status_code=303)


@router.get("/api-publica", response_class=HTMLResponse)
def api_publica(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    """Panel listo para activar y copiar la integración de la API pública."""
    base_url = os.getenv("SYSTEM_BASE_URL", "https://agenda.norem.cl").rstrip("/")
    return templates.TemplateResponse("admin_public_api.html", {"request": request, "current_user": cred, "agenda_url": f"{base_url}/cliente/{cred.tenant_id}/agendar_web"})


@router.post("/configuracion-negocio")
async def guardar_configuracion_negocio(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    if cred.rol not in {"admin", "superadmin"}:
        raise HTTPException(status_code=403, detail="Sólo el administrador puede configurar el negocio.")
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    form = await request.form()

    def entero(nombre: str, por_defecto: int, minimo: int, maximo: int) -> int:
        try:
            return max(minimo, min(int(form.get(nombre) or por_defecto), maximo))
        except (TypeError, ValueError):
            return por_defecto

    nombre_empresa = (form.get("nombre_empresa") or "").strip()
    if not nombre_empresa:
        return RedirectResponse("/admin/configuracion-negocio?error=" + quote("Ingresa el nombre del negocio."), status_code=303)
    horario, errores = horarios.parsear_formulario(form)
    if errores:
        return RedirectResponse("/admin/configuracion-negocio?error=" + quote(" ".join(errores[:3])), status_code=303)

    config = _leer_config_tenant(tenant)
    equipos_config = [equipo.strip() for equipo in (form.get("equipos") or "").split(",") if equipo.strip()] or ["Agenda principal"]
    config["negocio"] = {
        "giro": (form.get("giro") or "").strip(),
        "servicio_principal": (form.get("servicio_principal") or "").strip(),
        "duracion_minutos": entero("duracion_minutos", 60, 15, 480),
        "equipos": equipos_config,
    }
    reglas = config.get("reglas_negocio", {}) if isinstance(config.get("reglas_negocio"), dict) else {}
    # El horario semanal reemplaza a los formatos antiguos (bloques fijos y pausa única).
    for clave in ("bloques_horarios", "pausa"):
        reglas.pop(clave, None)
    intervalo = entero("intervalo_minutos", 0, 0, 480)
    reglas.update({
        "horario_semanal": horario,
        "dias_habiles": sorted(int(dia) for dia, tramos in horario.items() if tramos),
        "intervalo_minutos": intervalo or None,
        "atiende_feriados": form.get("atiende_feriados") == "1",
        "dias_anticipacion": entero("dias_anticipacion", 30, 1, 365),
        "horas_minimas_anticipacion": entero("horas_minimas_anticipacion", 0, 0, 720),
    })
    config["reglas_negocio"] = reglas
    widgets = [widget for widget in form.getlist("dashboard_widgets") if widget in {"resumen", "disponibilidad", "tareas", "metricas", "analitica"}]
    config["dashboard"] = {"dias_disponibilidad": entero("dias_dashboard", 7, 1, 28), "widgets": widgets}
    notificaciones = config.get("notificaciones", {})
    notificaciones["enviar_ubicacion_google"] = form.get("enviar_ubicacion_google") == "1"
    config["notificaciones"] = notificaciones
    config["onboarding_completo"] = True
    tenant.nombre_empresa, tenant.config_json = nombre_empresa, json.dumps(config)
    db.commit()
    return RedirectResponse("/admin/configuracion-negocio?guardado=1", status_code=303)


@router.get("/suscripcion", response_class=HTMLResponse)
def ver_suscripcion(
    request: Request,
    estado: str = Query(None),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Cuenta no encontrada.")
    dias_restantes = max(0, (tenant.trial_fin - models.get_now_chile()).days + 1) if tenant.trial_fin and tenant.estado_suscripcion == "prueba" else 0
    return templates.TemplateResponse("admin_subscription.html", {
        "request": request, "current_user": cred, "tenant": tenant,
        "dias_restantes": dias_restantes, "estado_checkout": estado,
    })


@router.post("/suscripcion/checkout")
def iniciar_checkout_suscripcion(
    request: Request,
    db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)
):
    if cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede contratar la suscripción.")
    tenant_actual = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if tenant_actual and tenant_actual.estado_suscripcion == "activa" and (
        tenant_actual.mercado_pago_preapproval_id or tenant_actual.stripe_subscription_id
    ):
        # Evita una segunda suscripción (y un doble cobro) para un negocio que ya paga.
        return RedirectResponse("/admin/suscripcion", status_code=status.HTTP_303_SEE_OTHER)
    if os.getenv("MERCADOPAGO_ACCESS_TOKEN"):
        try:
            # El id de la suscripción se guarda recién cuando Mercado Pago la
            # autoriza (webhook). Así un intento abandonado nunca reemplaza a la
            # suscripción vigente ni puede cancelarla al vencer.
            checkout_url, _ = mercadopago_utils.crear_suscripcion_mensual(
                tenant_id=cred.tenant_id,
                payer_email=cred.email,
                back_url=f"{SYSTEM_BASE_URL}/admin/suscripcion?estado=pendiente",
            )
            return RedirectResponse(checkout_url, status_code=status.HTTP_303_SEE_OTHER)
        except RuntimeError as exc:
            tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
            return templates.TemplateResponse("admin_subscription.html", {
                "request": request, "current_user": cred, "tenant": tenant, "dias_restantes": 0, "error": str(exc),
            }, status_code=503)
    mercado_pago_url = os.getenv("MERCADOPAGO_NOREM_MENSUAL_URL")
    if mercado_pago_url:
        return RedirectResponse(mercado_pago_url, status_code=status.HTTP_303_SEE_OTHER)
    try:
        checkout_url = stripe_utils.create_norem_monthly_checkout_session(
            tenant_id=cred.tenant_id,
            success_url=f"{SYSTEM_BASE_URL}/admin/suscripcion",
            cancel_url=f"{SYSTEM_BASE_URL}/admin/suscripcion",
        )
    except RuntimeError as exc:
        tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
        return templates.TemplateResponse("admin_subscription.html", {
            "request": request, "current_user": cred, "tenant": tenant, "dias_restantes": 0, "error": str(exc),
        }, status_code=503)
    return RedirectResponse(checkout_url, status_code=status.HTTP_303_SEE_OTHER)


def _hash_reset_token(token: str) -> str:
    secret = os.getenv("PASSWORD_RESET_SECRET") or os.getenv("JWT_SECRET_KEY", "")
    return hashlib.sha256(f"{secret}:{token}".encode("utf-8")).hexdigest()


@router.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_form(request: Request):
    return templates.TemplateResponse("forgot_password.html", {"request": request})


@router.post("/forgot-password", response_class=HTMLResponse)
def forgot_password(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    # La misma respuesta para todos los correos evita revelar qué cuentas existen.
    usuario = db.query(models.Usuario).filter(models.Usuario.email == email.strip().lower()).first()
    if usuario:
        token = secrets.token_urlsafe(32)
        usuario.password_reset_token_hash = _hash_reset_token(token)
        usuario.password_reset_expires_at = models.get_now_chile() + timedelta(minutes=30)
        db.commit()
        reset_url = f"{SYSTEM_BASE_URL}/admin/reset-password?token={token}"
        if enviar_correo_recuperacion_contrasena(usuario.email, usuario.nombre, reset_url):
            logger.info("password_reset_smtp_accepted")
        else:
            # No dejamos activo un token que no llegó al destinatario.
            usuario.password_reset_token_hash = None
            usuario.password_reset_expires_at = None
            db.commit()
            logger.warning("password_reset_delivery_failed")
    else:
        logger.info("password_reset_account_not_found")
    return templates.TemplateResponse("forgot_password.html", {"request": request, "sent": True})


@router.get("/reset-password", response_class=HTMLResponse)
def reset_password_form(request: Request, token: str = ""):
    return templates.TemplateResponse("reset_password.html", {"request": request, "token": token})


@router.post("/reset-password", response_class=HTMLResponse)
def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db),
):
    if len(password) < 8:
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "error": "La contraseña debe tener al menos 8 caracteres."})
    if password != password_confirm:
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": token, "error": "Las contraseñas no coinciden."})

    usuario = db.query(models.Usuario).filter(
        models.Usuario.password_reset_token_hash == _hash_reset_token(token),
        models.Usuario.password_reset_expires_at >= models.get_now_chile(),
    ).first()
    if not usuario:
        return templates.TemplateResponse("reset_password.html", {"request": request, "token": "", "error": "Este enlace no es válido o ya venció."})

    usuario.password_hash = security.get_password_hash(password)
    usuario.password_reset_token_hash = None
    usuario.password_reset_expires_at = None
    usuario.sesion_activa = False
    db.commit()
    response = RedirectResponse(url="/admin/login?password_reset=1", status_code=status.HTTP_303_SEE_OTHER)
    _delete_session_cookie(response, request)
    return response


@router.get("/logout")
def logout(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    usuario = db.query(models.Usuario).filter(
        models.Usuario.id == cred.id,
        models.Usuario.tenant_id == cred.tenant_id,
    ).first()
    if usuario:
        usuario.sesion_activa = False
        db.commit()
    response = RedirectResponse(url="/admin/login", status_code=status.HTTP_303_SEE_OTHER)
    _delete_session_cookie(response, request)
    return response


# =============================
#   ENDPOINTS DE ADMIN
# =============================

@router.get("/agendamientos", response_model=List[schemas.AgendamientoOut])
def listar_agendamientos(db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    return db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id
    ).order_by(models.Agendamiento.fecha_inicio).all()


@router.get("/panel", response_class=HTMLResponse)
def panel_agendamientos(
    request: Request,
    tipo_servicio: str = Query(None),
    subtipo: str = Query(None),
    fecha: str = Query(None),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    query = db.query(models.Agendamiento).filter(models.Agendamiento.tenant_id == cred.tenant_id)

    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    try:
        tenant_config = json.loads(tenant.config_json or "{}")
    except Exception:
        tenant_config = {}

    if subtipo:
        filter_subtipo = subtipo.lower().strip()
        if filter_subtipo == "local":
            filter_subtipo = "taller"
        query = query.filter(models.Agendamiento.subtipo == filter_subtipo)
    if tipo_servicio:
        query = query.filter(models.Agendamiento.tipo_servicio == tipo_servicio)
    if fecha:
        try:
            fecha_inicio = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_fin = fecha_inicio + timedelta(days=1)
            query = query.filter(
                models.Agendamiento.fecha_inicio >= fecha_inicio,
                models.Agendamiento.fecha_inicio < fecha_fin
            )
        except ValueError:
            pass

    agendamientos = query.order_by(models.Agendamiento.id).all()
    utm_registro = db.query(models.UTMRegistro).filter(
        models.UTMRegistro.tenant_id == cred.tenant_id
    ).all()

    dias_bloqueados = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.tenant_id == cred.tenant_id
    ).all()

    equipos_config = tenant_config.get("negocio", {}).get("equipos", []) or ["Agenda principal"]
    paleta = ["#2563EB", "#059669", "#7C3AED", "#EA580C", "#DB2777"]
    colores = {equipo: paleta[index % len(paleta)] for index, equipo in enumerate(equipos_config)}
    
    eventos_lista = []

    for item in agendamientos:
        start_iso = item.fecha_inicio.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = item.fecha_termino.strftime("%Y-%m-%dT%H:%M:%S") if item.fecha_termino else start_iso

        # LIMPIEZA CLAVE: Evita que comillas o saltos de lÃ­nea rompan el JS
        nota_limpia = (item.nota_interna or "").replace('"', '\\"').replace('\n', ' ').replace('\r', '')

        eventos_lista.append({
            "id": str(item.id),
            "title": f"{item.nombre} {item.apellido}",
            "start": start_iso,
            "end": end_iso,
            "backgroundColor": colores.get(item.equipo, "#6C63FF"),
            "borderColor": colores.get(item.equipo, "#6C63FF"),
            "extendedProps": {
                "nombre": item.nombre or "",
                "apellido": item.apellido or "",
                "patente": item.patente or "S/P",
                "equipo": item.equipo or "Sin equipo",
                "subtipo": item.subtipo or "",
                "direccion": item.direccion or "",
                "nota": nota_limpia 
            }
        })

    # --- NUEVA LÃNEA 2: Agregamos los bloqueos al calendario ---
    for b in dias_bloqueados:
        eventos_lista.append({
            "id": str(b.id),
            "start": b.fecha.strftime("%Y-%m-%d"), # Solo fecha para que sea todo el dÃ­a
            "display": "background",              # Pinta el fondo del calendario
            "backgroundColor": "#FFDADA",         # Color rojo suave
            "extendedProps": { "tipo": "bloqueo" } # Identificador para JS
        })

    # Convertimos a string JSON
    eventos_json_str = json.dumps(eventos_lista)

    base_url = SYSTEM_BASE_URL
    links_agenda = {tenant_config.get("negocio", {}).get("servicio_principal") or "Agendar": f"{base_url}/cliente/{cred.tenant_id}/agendar_web"}

    return templates.TemplateResponse(
        name="admin_agendamientos.html",
        context={
            "request": request,  # AquÃ­ adentro sÃ­ va de nuevo si usas 'context='
            "agendamientos": agendamientos,
            "dias_bloqueados": dias_bloqueados,
            "tipo_servicio": tipo_servicio,
            "subtipo": subtipo,
            "eventos_json": eventos_json_str,
            "fecha": fecha,
            "utm_registro": utm_registro,
            "links_agenda": links_agenda,
            "current_user": cred,
            "tenant_config": tenant_config
            ,"equipos_config": equipos_config
        }
    )


@router.post("/actualizar_nota/{id}")
def actualizar_nota(
    id: int,
    nota: str = Form(...),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    # Buscamos el registro en la DB usando SQLAlchemy
    agendamiento = db.query(models.Agendamiento).filter(
        models.Agendamiento.id == id,
        models.Agendamiento.tenant_id == cred.tenant_id,
    ).first()
    
    if not agendamiento:
        return RedirectResponse("/admin/panel", status_code=303)

    # Actualizamos la nota interna
    agendamiento.nota_interna = nota
    
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("appointment_note_update_failed tenant_id=%s", cred.tenant_id)
    
    return RedirectResponse("/admin/panel", status_code=303)
# =============================
# Exportacion UTM
# ============================

@router.get("/export/utm")
def export_utm(
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agendamientos UTM"
    
    ws.append(["ID","Origen Link", "Canal","Creado Por","RUT","Nombre","Apellido","Direccion","Patente","Marca","Modelo","Fecha Inicio","Fecha Termino"])

    agendamientos = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id
    ).order_by(models.Agendamiento.fecha_inicio.desc()).all()
    
    for a in agendamientos: 
        ws.append([
            a.id,
            a.utm_link or "",
            a.utm_source_real or "",
            a.creado_en or "",
            a.rut,
            a.nombre, 
            a.apellido,
            a.direccion or "",
            a.patente,
            a.marca,
            a.modelo,
            a.fecha_inicio.strftime("%Y-%m-%d %H:%M:%S"),
            a.fecha_termino.strftime("%Y-%m-%d %H:%M:%S")
        ])
     # Guardar el archivo en un objeto BytesIO

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)

    return StreamingResponse(
        stream,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=utm_registros.xlsx"}
    )

@router.post("/cancelar/{id}")
def cancelar_agendamiento(
    id: int,
    db: Session = Depends(get_db),
    admin=Depends(verificar_login)
):
    ag = db.query(models.Agendamiento).filter(
        models.Agendamiento.id == id,
        models.Agendamiento.tenant_id == admin.tenant_id,
    ).first()

    if not ag:
        raise HTTPException(404, "Agendamiento no encontrado")

    ag.estado = "cancelado"
    db.commit()
    db.refresh(ag)

    enviar_correo_cancelacion(ag)

    return RedirectResponse(
        url="/admin/panel",
        status_code=303
    )


# ENVIAR LINKS POR ADMIN
@router.get("/links-agenda")
def obtener_links_agenda(request: Request, db: Session = Depends(get_db), admin: CurrentUser = Depends(verificar_login)):
    """Links de agenda del propio negocio (cada tenant tiene su URL pública)."""
    agenda = f"{SYSTEM_BASE_URL}/cliente/{admin.tenant_id}/agendar_web"
    links = {
        "local": {
            "label": "Agendar Servicio",
            "url": f"{agenda}?tipo=domicilio_taller&subtipo=local",
        }
    }
    # El link a domicilio sólo se ofrece si el negocio armó ese formulario.
    tiene_domicilio = db.query(models.CampoFormulario.id).filter(
        models.CampoFormulario.tenant_id == admin.tenant_id,
        models.CampoFormulario.subtipo_servicio == "domicilio",
        models.CampoFormulario.activo == True,
    ).first()
    if tiene_domicilio:
        links["domicilio"] = {
            "label": "Servicio a Domicilio",
            "url": f"{agenda}?tipo=domicilio_taller&subtipo=domicilio",
        }
    links["especializado"] = {
        "label": "Equipo Especializado",
        **{horas: f"{agenda}?tipo=especializado&duracion_horas={horas}" for horas in (2, 3, 4)},
    }
    return links
# ==========================================
#   GESTIÃN DE FORMULARIO DINÃMICO
# ==========================================

@router.get("/configurar-formulario")
def configurar_formulario(
    request: Request,
    subtipo: str = "local", # Por defecto local
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    raw_subtipo = subtipo.lower().strip() if subtipo else "local"
    db_subtipo = "taller" if raw_subtipo == "local" else raw_subtipo

    # Buscamos los campos que coincidan con el subtipo seleccionado
    campos = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.tenant_id == cred.tenant_id,
        models.CampoFormulario.subtipo_servicio == db_subtipo
    ).order_by(models.CampoFormulario.orden.asc()).all()

    return templates.TemplateResponse("admin_config_form.html", {
        "request": request,
        "campos": campos,
        "subtipo_actual": raw_subtipo,
        "current_user": cred
    })
@router.post("/configurar-formulario/guardar")
async def guardar_campo(
    campo_id: Optional[int] = Form(None),
    subtipo_servicio: str = Form(...),
    label: Optional[str] = Form(None), # Permitir que sea None inicialmente
    tipo_campo: str = Form(...),
    opciones: Optional[str] = Form(None),
    obligatorio: bool = Form(False),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    # VALIDACIÃN: Si label es None, le damos un valor por defecto para que no explote
    texto_label = label if label else "Campo sin nombre"
    raw_subtipo = subtipo_servicio.lower().strip()
    db_subtipo = "taller" if raw_subtipo == "local" else raw_subtipo
    
    # Ahora procesamos el nombre tÃ©cnico con seguridad
    nombre_tecnico = texto_label.lower().strip().replace(" ", "_")

    # Mapeo inteligente para campos crÃ­ticos de la tabla Agendamiento
    if any(x in nombre_tecnico for x in ["correo", "email", "mail"]):
        nombre_tecnico = "correo"
    elif any(x in nombre_tecnico for x in ["rut", "identificacion", "dni"]):
        nombre_tecnico = "rut"
    elif "nombre" in nombre_tecnico and "apellido" not in nombre_tecnico:
        nombre_tecnico = "nombre"
    elif "apellido" in nombre_tecnico:
        nombre_tecnico = "apellido"
    elif any(x in nombre_tecnico for x in ["telefono", "celular", "movil", "whatsapp"]):
        nombre_tecnico = "telefono"
    elif any(x in nombre_tecnico for x in ["kilometr", "km"]):
        nombre_tecnico = "kilometraje"
    elif "marca" in nombre_tecnico:
        nombre_tecnico = "marca"
    elif "modelo" in nombre_tecnico:
        nombre_tecnico = "modelo"
    elif "patente" in nombre_tecnico or "placa" in nombre_tecnico:
        nombre_tecnico = "patente"
    elif "direccion" in nombre_tecnico or "calle" in nombre_tecnico:
        nombre_tecnico = "direccion"
    elif "vivienda" in nombre_tecnico or "casa" in nombre_tecnico:
        nombre_tecnico = "tipo_vivienda"

    if campo_id:
        campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id, models.CampoFormulario.tenant_id == cred.tenant_id).first()
        if campo:
            campo.subtipo_servicio = db_subtipo
            campo.label = texto_label
            campo.tipo_campo = tipo_campo
            campo.opciones = opciones
            campo.obligatorio = obligatorio
            campo.nombre_tecnico = nombre_tecnico
    else:
        nuevo = models.CampoFormulario(
            tenant_id=cred.tenant_id,
            subtipo_servicio=db_subtipo,
            label=texto_label,
            nombre_tecnico=nombre_tecnico,
            tipo_campo=tipo_campo,
            opciones=opciones,
            obligatorio=obligatorio
        )
        db.add(nuevo)

    db.commit()
    return RedirectResponse(url=f"/admin/configurar-formulario?subtipo={raw_subtipo}", status_code=303)

@router.get("/configurar-formulario/eliminar/{campo_id}")
async def eliminar_campo(campo_id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    # 1. Buscamos el campo en la base de datos
    campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id, models.CampoFormulario.tenant_id == cred.tenant_id).first()
    
    if not campo:
        print(f"No se encontrÃ³ el campo con ID {campo_id}")
        return RedirectResponse(url="/admin/configurar-formulario", status_code=303)

    # Guardamos el subtipo para poder redireccionar al mismo sitio despuÃ©s
    subtipo_servicio = "local" if campo.subtipo_servicio == "taller" else campo.subtipo_servicio

    # 2. Lo eliminamos
    db.delete(campo)
    db.commit()

    print(f"Campo {campo_id} eliminado correctamente")
    
    # 3. Redirigimos de vuelta a la configuraciÃ³n de ese subtipo
    return RedirectResponse(
        url=f"/admin/configurar-formulario?subtipo={subtipo_servicio}", 
        status_code=303
    )

@router.post("/configurar-formulario/reordenar")
async def reordenar_campos(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    posiciones = payload.get("posiciones", [])
    
    try:
        for item in posiciones:
            # Buscamos el campo por su ID
            campo = db.query(models.CampoFormulario).filter(
                models.CampoFormulario.id == int(item['id']),
                models.CampoFormulario.tenant_id == cred.tenant_id
            ).first()
            
            if campo:
                campo.orden = item['orden']
        
        db.commit()
        return {"status": "success", "message": "Orden actualizado"}
    
    except Exception:
        db.rollback()
        logger.error("form_fields_reorder_failed tenant_id=%s", cred.tenant_id)
        raise HTTPException(status_code=500, detail="No se pudo guardar el orden de los campos")



@router.post("/configurar-formulario/editar/{campo_id}")
def editar_campo(
    campo_id: int,
    label: str = Form(...),
    tipo_campo: str = Form(...),
    opciones: str = Form(None),
    obligatorio: str = Form(None),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id, models.CampoFormulario.tenant_id == cred.tenant_id).first()
    if not campo:
        return RedirectResponse("/admin/editor-visual-formulario", status_code=303)

    campo.label = label
    campo.tipo_campo = tipo_campo
    campo.opciones = opciones
    campo.obligatorio = True if obligatorio == "on" else False

    db.commit()
    subtipo_redirect = "local" if campo.subtipo_servicio == "taller" else campo.subtipo_servicio
    return RedirectResponse(f"/admin/configurar-formulario?subtipo={subtipo_redirect}", status_code=303)


class ReprogramarCitaSchema(BaseModel):
    fecha_inicio: datetime


def verificar_disponibilidad_detalle(
    db: Session,
    tipo_servicio: str,
    inicio: datetime,
    duracion_horas: float,
    excluir_id: Optional[int] = None,
    tenant_id: str = "default",
    duracion_minutos: Optional[int] = None,
) -> Tuple[bool, str]:
    """Valida un cambio de horario hecho por el negocio según SU horario configurado."""
    inicio = inicio.replace(tzinfo=None)
    minutos = duracion_minutos if duracion_minutos else int(round(float(duracion_horas) * 60))
    fin = inicio + timedelta(minutes=minutos)

    dia_bloqueado = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.fecha == inicio.date(),
        models.DiaBloqueado.tenant_id == tenant_id
    ).first()
    if dia_bloqueado:
        return False, f"El día {inicio.strftime('%d/%m/%Y')} está bloqueado ({dia_bloqueado.motivo or 'Cerrado'})."

    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    config = _leer_config_tenant(tenant) if tenant else {}

    if horarios.cerrado_por_feriado(config, inicio.date()):
        return False, f"El {inicio.strftime('%d/%m/%Y')} es feriado ({horarios.nombre_feriado(inicio.date())}) y tu agenda no atiende feriados."

    dia_semana = inicio.weekday()
    if not horarios.cabe_en_horario(config, inicio, fin):
        horario_dia = horarios.describir_horario(config, dia_semana)
        nombre_dia = horarios.DIAS_SEMANA[dia_semana]
        if horario_dia == "Cerrado":
            return False, f"Tu agenda está cerrada los {nombre_dia.lower()}."
        return False, (
            f"La cita ({inicio.strftime('%H:%M')}–{fin.strftime('%H:%M')}) queda fuera de tu horario "
            f"del {nombre_dia.lower()}: {horario_dia}."
        )

    query = db.query(models.Agendamiento).filter(
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio,
        models.Agendamiento.estado != "cancelado",
        models.Agendamiento.tenant_id == tenant_id
    )
    if excluir_id is not None:
        query = query.filter(models.Agendamiento.id != excluir_id)

    limite_equipos = max(1, len(equipos_configurados(tenant)))
    if query.count() >= limite_equipos:
        return False, f"No hay equipos disponibles en este horario (máximo {limite_equipos} citas simultáneas)."

    return True, ""


@router.post("/reprogramar-cita/{id}")
async def reprogramar_cita(
    id: int,
    payload: ReprogramarCitaSchema,
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    ag = db.query(models.Agendamiento).filter(
        models.Agendamiento.id == id,
        models.Agendamiento.tenant_id == admin.tenant_id,
    ).first()
    if not ag:
        return {"status": "error", "message": "Cita no encontrada"}
        
    inicio_nueva = payload.fecha_inicio
    
    # Asegurar zona horaria de Chile
    tz_chile = pytz.timezone("America/Santiago")
    if inicio_nueva.tzinfo is None:
        inicio_nueva = tz_chile.localize(inicio_nueva)
    else:
        inicio_nueva = inicio_nueva.astimezone(tz_chile)
        
    # Quitar tzinfo para guardar en sqlite
    inicio_nueva_naive = inicio_nueva.replace(tzinfo=None)
    
    # Mantener la duración real de la cita (puede ser en minutos).
    if ag.fecha_inicio and ag.fecha_termino and ag.fecha_termino > ag.fecha_inicio:
        minutos_cita = int((ag.fecha_termino - ag.fecha_inicio).total_seconds() // 60)
    else:
        minutos_cita = int((ag.duracion_horas or 1) * 60)
    fin_nueva_naive = inicio_nueva_naive + timedelta(minutes=minutos_cita)

    # Verificar disponibilidad
    disponible, msg_error = verificar_disponibilidad_detalle(
        db=db,
        tipo_servicio=getattr(ag.tipo_servicio, "value", ag.tipo_servicio),
        inicio=inicio_nueva_naive,
        duracion_horas=minutos_cita / 60,
        excluir_id=ag.id,
        tenant_id=admin.tenant_id,
        duracion_minutos=minutos_cita,
    )
    
    if not disponible:
        return {"status": "error", "message": msg_error}
        
    # Asignar equipo disponible
    tenant_reprogramar = db.query(models.Tenant).filter(models.Tenant.id == admin.tenant_id).first()
    equipos_posibles = equipos_configurados(tenant_reprogramar)
    equipo_asignado = None
    
    # 1. Intentar con el equipo actual
    current_team = ag.equipo
    if current_team in equipos_posibles:
        ocupado = db.query(models.Agendamiento).filter(
            models.Agendamiento.tenant_id == admin.tenant_id,
            models.Agendamiento.id != ag.id,
            models.Agendamiento.equipo == current_team,
            models.Agendamiento.fecha_inicio < fin_nueva_naive,
            models.Agendamiento.fecha_termino > inicio_nueva_naive,
            models.Agendamiento.estado != "cancelado"
        ).first()
        if not ocupado:
            equipo_asignado = current_team
            
    # 2. Si el actual estÃ¡ ocupado, buscar otro
    if not equipo_asignado:
        for eq in equipos_posibles:
            if eq == current_team:
                continue
            ocupado = db.query(models.Agendamiento).filter(
                models.Agendamiento.tenant_id == admin.tenant_id,
                models.Agendamiento.id != ag.id,
                models.Agendamiento.equipo == eq,
                models.Agendamiento.fecha_inicio < fin_nueva_naive,
                models.Agendamiento.fecha_termino > inicio_nueva_naive,
                models.Agendamiento.estado != "cancelado"
            ).first()
            if not ocupado:
                equipo_asignado = eq
                break
                
    if not equipo_asignado:
        return {"status": "error", "message": "No se encontrÃ³ un equipo disponible para este horario."}
        
    # Guardar cambios
    ahora_str = datetime.now(tz_chile).strftime("%H:%M")
    log_reprogramacion = f"\n[REPROGRAMACIÃN {ahora_str}]: {ag.fecha_inicio.strftime('%d/%m %H:%M')} ({ag.equipo}) -> {inicio_nueva_naive.strftime('%d/%m %H:%M')} ({equipo_asignado})"
    
    ag.fecha_inicio = inicio_nueva_naive
    ag.fecha_termino = fin_nueva_naive
    ag.equipo = equipo_asignado
    ag.nota_interna = (ag.nota_interna or "") + log_reprogramacion
    
    try:
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        logger.exception("booking_reschedule_failed", extra={"booking_id": id, "tenant_id": admin.tenant_id})
        return {"status": "error", "message": "No se pudo guardar la reprogramación. Intenta nuevamente."}


@router.post("/reubicar-emergencia/{id}")
async def reubicar_emergencia(
    id: int, 
    payload: dict = Body(...), 
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    nueva_direccion = payload.get("nueva_direccion")
    ag = db.query(models.Agendamiento).filter(
        models.Agendamiento.id == id,
        models.Agendamiento.tenant_id == admin.tenant_id,
    ).first()
    
    if not ag:
        return {"status": "error", "message": "No encontrado"}

    ahora = datetime.now().strftime("%H:%M")
    log = f"\n[REUBICACIÃN {ahora}]: {ag.direccion} -> {nueva_direccion}"
    
    ag.direccion = nueva_direccion
    ag.nota_interna = (ag.nota_interna or "") + log
    # Guardamos una marca de modificaciÃ³n para el estilo visual
    ag.modificado = True 
    
    db.commit()
    return {"status": "ok"}

# 1. Definimos la estructura que esperamos recibir del JS
class BloqueoDiaSchema(BaseModel):
    fecha: str
    motivo: Optional[str] = None


def _cancelar_y_notificar_citas_del_dia(db: Session, tenant_id: str, fecha_dt, motivo: Optional[str]) -> Tuple[int, int]:
    """Cancela solo las citas activas de ese tenant y día, y avisa una vez a cada una."""
    inicio_dia = datetime.combine(fecha_dt, dt_time.min)
    fin_dia = inicio_dia + timedelta(days=1)
    citas = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio >= inicio_dia,
        models.Agendamiento.fecha_inicio < fin_dia,
        models.Agendamiento.estado != "cancelado",
    ).all()
    for cita in citas:
        cita.estado = "cancelado"
    db.commit()

    notificaciones_enviadas = 0
    for cita in citas:
        if cita.correo and enviar_correo_cancelacion_por_bloqueo(cita, motivo):
            notificaciones_enviadas += 1
    return len(citas), notificaciones_enviadas

@router.post("/bloquear-dia-completo")
def bloquear_dia(datos: BloqueoDiaSchema, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    # Ahora accedemos a datos.fecha en lugar de un Form
    try:
        fecha_dt = datetime.strptime(datos.fecha, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Formato de fecha invÃ¡lido"}, 400
    
    # Verificamos que no exista ya
    existe = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.tenant_id == cred.tenant_id,
        models.DiaBloqueado.fecha == fecha_dt
    ).first()
    
    if not existe:
        nuevo = models.DiaBloqueado(tenant_id=cred.tenant_id, fecha=fecha_dt, motivo=datos.motivo)
        db.add(nuevo)
        db.commit()
        citas_canceladas, correos_enviados = _cancelar_y_notificar_citas_del_dia(
            db, cred.tenant_id, fecha_dt, datos.motivo
        )
    else:
        citas_canceladas, correos_enviados = 0, 0
    
    
    # Como es una peticiÃ³n AJAX (fetch), es mejor devolver un JSON de Ã©xito 
    # en lugar de un RedirectResponse, para que el JS haga el reload.
    return {"status": "success", "message": "DÃ­a bloqueado correctamente", "citas_canceladas": citas_canceladas, "correos_enviados": correos_enviados}

@router.post("/bloquear-dia")
def bloquear_dia_formulario(
    fecha: str = Form(...),
    motivo: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    try:
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha invÃ¡lido")
    
    existe = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.tenant_id == admin.tenant_id,
        models.DiaBloqueado.fecha == fecha_dt
    ).first()
    if not existe:
        nuevo = models.DiaBloqueado(tenant_id=admin.tenant_id, fecha=fecha_dt, motivo=motivo)
        db.add(nuevo)
        db.commit()
        _cancelar_y_notificar_citas_del_dia(db, admin.tenant_id, fecha_dt, motivo)
    
    return RedirectResponse(url="/admin/panel", status_code=303)

@router.post("/desbloquear-dia/{id}")
def desbloquear_dia(id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    dia = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.id == id,
        models.DiaBloqueado.tenant_id == cred.tenant_id
    ).first()
    if dia:
        db.delete(dia)
        db.commit()
        print(f"DEBUG: DÃ­a {id} desbloqueado con Ã©xito")
        return {"status": "ok", "message": "DÃ­a eliminado"} # Cambiamos la redirecciÃ³n por JSON
    
    return {"status": "error", "message": "No se encontrÃ³ el registro"}, 404


@router.post("/editar-cita/{id}")
async def editar_cita_admin(
    id: int, 
    fecha: str = Form(...), 
    hora: str = Form(...), 
    duracion_horas: int = Form(...), 
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    cita = db.query(models.Agendamiento).filter(
        models.Agendamiento.id == id,
        models.Agendamiento.tenant_id == admin.tenant_id,
    ).first()
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
        
    try:
        nueva_fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        nueva_fecha_termino = nueva_fecha_inicio + timedelta(hours=duracion_horas)
        
        cita.fecha_inicio = nueva_fecha_inicio
        cita.fecha_termino = nueva_fecha_termino
        cita.duracion_horas = duracion_horas
        
        db.commit()
    except Exception:
        db.rollback()
        logger.error("appointment_reschedule_failed tenant_id=%s", admin.tenant_id)
        raise HTTPException(status_code=500, detail="No se pudo actualizar la cita")
        
    return RedirectResponse(url="/admin/panel", status_code=303)

@router.get("/api/bloqueos")
def obtener_bloqueos_json(db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    """API que devuelve bloqueos en formato JSON para FullCalendar"""
    import json
    dias_bloqueados = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.tenant_id == cred.tenant_id
    ).all()
    
    bloqueos = []
    for b in dias_bloqueados:
        bloqueos.append({
            "id": str(b.id),
            "start": b.fecha.strftime("%Y-%m-%d"),
            "display": "background",
            "backgroundColor": "#FFDADA",
            "extendedProps": { "tipo": "bloqueo", "motivo": b.motivo or "DÃ­a bloqueado" }
        })
    
    return bloqueos

@router.get("/api/debug/agendamientos")
def debug_agendamientos(db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    """Endpoint de debugging para ver todos los agendamientos"""
    agendamientos = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id
    ).all()
    
    resultado = []
    for ag in agendamientos:
        resultado.append({
            "id": ag.id,
            "nombre": ag.nombre,
            "apellido": ag.apellido,
            "subtipo": ag.subtipo,
            "tipo_servicio": ag.tipo_servicio,
            "equipo": ag.equipo,
            "fecha_inicio": ag.fecha_inicio.isoformat() if ag.fecha_inicio else None,
            "estado": ag.estado,
        })
    
    return {"total": len(resultado), "agendamientos": resultado}

@router.get("/api/debug/ultimo-agendamiento")
def debug_ultimo_agendamiento(db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    """Endpoint de debugging para ver el Ãºltimo agendamiento guardado"""
    ultimo = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id
    ).order_by(models.Agendamiento.id.desc()).first()
    
    if not ultimo:
        return {"error": "No hay agendamientos"}
    
    return {
        "id": ultimo.id,
        "nombre": f"{ultimo.nombre} {ultimo.apellido}",
        "subtipo": ultimo.subtipo,
        "tipo_servicio": ultimo.tipo_servicio,
        "equipo": ultimo.equipo,
        "fecha_inicio": ultimo.fecha_inicio.isoformat() if ultimo.fecha_inicio else None,
        "estado": ultimo.estado,
        "creado_en": ultimo.creado_en.isoformat() if hasattr(ultimo, 'creado_en') and ultimo.creado_en else "N/A"
    }

@router.get("/agendar-emergencia-total")
async def agendar_emergencia(request: Request, cred: CurrentUser = Depends(verificar_login)):
    """Modo sobrecupo: abre la agenda del propio negocio en modo dueño."""
    target_url = f"/cliente/{cred.tenant_id}/agendar_web?tipo=domicilio_taller&subtipo=local&modo=emergencia"
    return RedirectResponse(url=target_url)


@router.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(
    request: Request,
    desde: str = Query(None),
    hasta: str = Query(None),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    # Filtro global base (Aislamiento de Tenant)
    query = db.query(models.Agendamiento).filter(models.Agendamiento.tenant_id == cred.tenant_id)
    if desde:
        try:
            d_dt = datetime.strptime(desde, "%Y-%m-%d")
            query = query.filter(models.Agendamiento.fecha_inicio >= d_dt)
        except ValueError:
            pass
    if hasta:
        try:
            h_dt = datetime.strptime(hasta, "%Y-%m-%d")
            query = query.filter(models.Agendamiento.fecha_inicio <= h_dt.replace(hour=23, minute=59, second=59))
        except ValueError:
            pass

    # Total de citas
    total_citas = query.count()
    
    tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(tz)
    hoy_dt = ahora.replace(hour=0, minute=0, second=0, microsecond=0)
    fin_hoy_dt = hoy_dt + timedelta(days=1)
    inicio_semana = hoy_dt - timedelta(days=hoy_dt.weekday())
    inicio_mes = hoy_dt.replace(day=1)
    
    agendas_hoy = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id,
        models.Agendamiento.fecha_inicio >= hoy_dt.replace(tzinfo=None), 
        models.Agendamiento.fecha_inicio < fin_hoy_dt.replace(tzinfo=None)
    ).count()
    
    agendas_semana = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id,
        models.Agendamiento.fecha_inicio >= inicio_semana.replace(tzinfo=None)
    ).count()
    
    agendas_mes = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == cred.tenant_id,
        models.Agendamiento.fecha_inicio >= inicio_mes.replace(tzinfo=None)
    ).count()
    
    tareas_activas = db.query(models.Tarea).filter(
        models.Tarea.tenant_id == cred.tenant_id,
        models.Tarea.estado.notin_(["Completada", "Cancelada"])
    ).count()
    
    tareas_vencidas = db.query(models.Tarea).filter(
        models.Tarea.tenant_id == cred.tenant_id,
        models.Tarea.fecha_limite < ahora.replace(tzinfo=None), 
        models.Tarea.estado.notin_(["Completada", "Cancelada"])
    ).count()

    filtro_agenda_web = or_(
        models.Agendamiento.utm_source_real == ORIGEN_AGENDA_WEB,
        models.Agendamiento.nota_interna == "Reserva creada desde API pública",
    )
    agendas_desde_web = query.filter(filtro_agenda_web).count()
    lista_agendas_web = query.filter(
        filtro_agenda_web
    ).order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()
    
    # Capacidad Futura (Mejora 7)
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    try:
        tenant_config = json.loads(tenant.config_json or "{}")
    except (AttributeError, ValueError, TypeError, json.JSONDecodeError):
        tenant_config = {}
    horizonte_reservas = max(1, min(int(tenant_config.get("reglas_negocio", {}).get("dias_anticipacion", 30)), 365))
    equipos_tenant = max(1, len(equipos_configurados(tenant)))

    def capacidad_del_dia(dia) -> int:
        """Citas que caben ese día según el horario y los equipos del negocio."""
        if horarios.cerrado_por_feriado(tenant_config, dia.date()):
            return 0
        return len(horarios.inicios_del_dia(tenant_config, dia.weekday())) * equipos_tenant

    def get_capacidad_rango(dias: int):
        fecha_fin = hoy_dt + timedelta(days=dias)
        capacidad_total = sum(capacidad_del_dia(hoy_dt + timedelta(days=i)) for i in range(dias))
        ocupado = db.query(models.Agendamiento).filter(
            models.Agendamiento.tenant_id == cred.tenant_id,
            models.Agendamiento.fecha_inicio >= hoy_dt.replace(tzinfo=None),
            models.Agendamiento.fecha_inicio < fecha_fin.replace(tzinfo=None),
            models.Agendamiento.estado != "cancelado"
        ).count()
        disponible = max(0, capacidad_total - ocupado)
        porcentaje = round((ocupado / capacidad_total) * 100, 1) if capacidad_total > 0 else 0
        estado = "Saturado" if porcentaje > 80 else ("Media" if porcentaje > 50 else "Libre")
        return {"disponible": disponible, "total": capacidad_total, "porcentaje": porcentaje, "estado": estado, "ocupado": ocupado}

    capacidad = get_capacidad_rango(horizonte_reservas)

    # Disponibilidad dÃ­a a dÃ­a de la semana (Mejora: vista semanal para el cliente interno)
    DIAS_ES = ["Lun", "Mar", "MiÃ©", "Jue", "Vie", "SÃ¡b", "Dom"]
    dias_habiles = horarios.dias_abiertos(tenant_config) or {0, 1, 2, 3, 4}

    def get_disponibilidad_dias(cantidad_dias_habiles: int):
        resultado = []
        dia = hoy_dt
        while len(resultado) < cantidad_dias_habiles:
            if dia.weekday() not in dias_habiles:
                dia += timedelta(days=1)
                continue

            es_feriado = horarios.cerrado_por_feriado(tenant_config, dia.date())
            nombre_feriado = horarios.nombre_feriado(dia.date()) if es_feriado else None

            bloqueo = db.query(models.DiaBloqueado).filter(
                models.DiaBloqueado.tenant_id == cred.tenant_id,
                models.DiaBloqueado.fecha == dia.date()
            ).first()
            ocupado = db.query(models.Agendamiento).filter(
                models.Agendamiento.tenant_id == cred.tenant_id,
                models.Agendamiento.fecha_inicio >= dia.replace(tzinfo=None),
                models.Agendamiento.fecha_inicio < (dia + timedelta(days=1)).replace(tzinfo=None),
                models.Agendamiento.estado != "cancelado"
            ).count()

            capacidad_dia = 0 if (bloqueo or es_feriado) else capacidad_del_dia(dia)
            porcentaje = round((ocupado / capacidad_dia) * 100, 1) if capacidad_dia > 0 else 100

            if bloqueo or es_feriado:
                estado_dia = "Feriado" if es_feriado and not bloqueo else "Bloqueado"
            elif porcentaje > 80:
                estado_dia = "Saturado"
            elif porcentaje > 50:
                estado_dia = "Media"
            else:
                estado_dia = "Libre"

            resultado.append({
                "fecha": dia,
                "dia_nombre": DIAS_ES[dia.weekday()],
                "ocupado": ocupado,
                "capacidad": capacidad_dia,
                "porcentaje": porcentaje,
                "estado": estado_dia,
                "motivo_bloqueo": nombre_feriado if es_feriado else (bloqueo.motivo if bloqueo else None)
            })
            dia += timedelta(days=1)
        return resultado
        return resultado

    dashboard_config = tenant_config.get("dashboard", {}) if 'tenant_config' in locals() else {}
    dias_dashboard = dashboard_config.get("dias_disponibilidad", len(dias_habiles))
    disponibilidad_semana = get_disponibilidad_dias(max(1, min(int(dias_dashboard), 28)))

    # Citas por estado
    confirmadas = query.filter(models.Agendamiento.estado == "confirmado").count()
    pendientes = query.filter(models.Agendamiento.estado == "pendiente").count()
    canceladas = query.filter(models.Agendamiento.estado == "cancelado").count()
    
    # Tasa de confirmaciÃ³n
    tasa_confirmacion = 0.0
    if (confirmadas + pendientes) > 0:
        tasa_confirmacion = round((confirmadas / (confirmadas + pendientes)) * 100, 1)
        
    # DistribuciÃ³n por subtipo (Taller/Local vs Domicilio)
    servicios_raw = query.with_entities(
        models.Agendamiento.subtipo,
        func.count(models.Agendamiento.id)
    ).group_by(models.Agendamiento.subtipo).all()
    
    servicios_labels = []
    servicios_valores = []
    for sub, count in servicios_raw:
        servicios_labels.append(tenant_config.get("negocio", {}).get("servicio_principal") or "Reservas")
        servicios_valores.append(count)
        
    # Carga de trabajo por equipo (excluyendo cancelados)
    equipos_raw = query.with_entities(
        models.Agendamiento.equipo,
        func.count(models.Agendamiento.id)
    ).filter(models.Agendamiento.estado != "cancelado").group_by(models.Agendamiento.equipo).all()
    
    equipos_labels = [eq if eq else "Sin Equipo" for eq, _ in equipos_raw]
    equipos_valores = [count for _, count in equipos_raw]
    
    
    # Canales UTM
    utm_raw = query.with_entities(
        models.Agendamiento.utm_source_real,
        func.count(models.Agendamiento.id)
    ).group_by(models.Agendamiento.utm_source_real).order_by(func.count(models.Agendamiento.id).desc()).all()
    
    utm_stats = []
    for utm, count in utm_raw:
        source = utm if utm else "Directo (Sin UTM)"
        utm_stats.append({"origen": source, "cantidad": count})
    
    # Datos mensuales para ver tendencia (Ajustado para PostgreSQL)
    tendencia_raw = query.with_entities(
        func.to_char(models.Agendamiento.fecha_inicio, 'YYYY-MM').label("mes"),
        func.count(models.Agendamiento.id)
    ).group_by(text("1")).order_by(text("1")).all()
    
    tendencia_labels = [str(mes) for mes, _ in tendencia_raw if mes]
    tendencia_valores = [count for _, count in tendencia_raw if count]

    # Listas recientes para paneles
    lista_confirmadas = query.filter(models.Agendamiento.estado == "confirmado").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()
    lista_pendientes = query.filter(models.Agendamiento.estado == "pendiente").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()
    lista_canceladas = query.filter(models.Agendamiento.estado == "cancelado").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()

    # Top 10 Tareas Urgentes (Mejora 8)
    tareas_activas_list = db.query(models.Tarea).filter(
        models.Tarea.tenant_id == cred.tenant_id,
        models.Tarea.estado.notin_(["Completada", "Cancelada"]),
    ).all()
    
    def puntaje_tarea(t):
        p_score = {"CrÃ­tica": 4, "Alta": 3, "Media": 2, "Baja": 1}.get(t.prioridad, 0)
        v_score = 0
        if t.fecha_limite:
            dias_restantes = (t.fecha_limite.replace(tzinfo=None) - ahora.replace(tzinfo=None)).days
            if dias_restantes < 0:
                v_score = 10  # Vencida! muy urgente
            elif dias_restantes <= 2:
                v_score = 5
            elif dias_restantes <= 7:
                v_score = 2
        return p_score + v_score
        
    top_tareas = sorted(tareas_activas_list, key=puntaje_tarea, reverse=True)[:10]

    resumen_kanban = {estado: len(tareas) for estado, tareas in crud_team.get_tareas_kanban(db, cred.tenant_id).items()}

    stats = {
        "agendas_hoy": agendas_hoy,
        "agendas_semana": agendas_semana,
        "agendas_mes": agendas_mes,
        "tareas_activas": tareas_activas,
        "tareas_vencidas": tareas_vencidas,
        "agendas_desde_web": agendas_desde_web,
        "capacidad": capacidad,
        "horizonte_reservas": horizonte_reservas,
        "disponibilidad_semana": disponibilidad_semana,
        "resumen_kanban": resumen_kanban,
        "total": total_citas,
        "confirmadas": confirmadas,
        "pendientes": pendientes,
        "canceladas": canceladas,
        "tasa_confirmacion": tasa_confirmacion,
        "servicios_labels": json.dumps(servicios_labels),
        "servicios_valores": json.dumps(servicios_valores),
        "equipos_labels": json.dumps(equipos_labels),
        "equipos_valores": json.dumps(equipos_valores),
        "utm_stats": utm_stats,
        "tendencia_labels": json.dumps(tendencia_labels),
        "tendencia_valores": json.dumps(tendencia_valores)
    }

    listas = {
        "confirmadas": lista_confirmadas,
        "pendientes": lista_pendientes,
        "canceladas": lista_canceladas,
        "top_tareas": top_tareas,
        "web_directas": lista_agendas_web,
    }

    return templates.TemplateResponse(
        name="admin_dashboard.html",
        context={"request": request, "stats": stats, "listas": listas, "current_user": cred, "dashboard_widgets": dashboard_config.get("widgets", ["resumen", "disponibilidad", "tareas", "metricas", "analitica"])}
    )

# ==========================================
#   GESTIÓN DE TENANTS (SUPERADMIN)
# ==========================================

@router.get("/tenants", response_class=HTMLResponse)
def listar_tenants(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    # Validar que sea superadmin (tenant default y rol admin)
    if cred.tenant_id != "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de SuperAdmin.")
        
    verificar_superadmin(cred)
    tenants_raw = db.query(models.Tenant).all()
    limite_sesion = models.get_now_chile() - timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    tenants_data = []
    for t in tenants_raw:
        admin_user = db.query(models.Usuario).filter(models.Usuario.tenant_id == t.id, models.Usuario.rol == "admin").first()
        try:
            tenant_config = json.loads(t.config_json or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            tenant_config = {}
        public_api = tenant_config.get("public_api", {})
        if not isinstance(public_api, dict):
            public_api = {}
        allowed_origins = public_api.get("allowed_origins", [])
        if not isinstance(allowed_origins, list):
            allowed_origins = []
        allowed_origins = [str(origin).strip() for origin in allowed_origins if str(origin).strip()]
        api_configurada = bool(public_api.get("enabled") and allowed_origins)
        integracion_query = db.query(models.Agendamiento).filter(
            models.Agendamiento.tenant_id == t.id,
            models.Agendamiento.utm_source_real.in_([ORIGEN_AGENDA_WEB, "API pública"]),
        )
        reservas_api = integracion_query.count()
        if not allowed_origins and reservas_api:
            allowed_origins = [origin for (origin,) in db.query(
                models.Agendamiento.utm_link
            ).filter(
                models.Agendamiento.tenant_id == t.id,
                models.Agendamiento.utm_source_real.in_([ORIGEN_AGENDA_WEB, "API pública"]),
                models.Agendamiento.utm_link.isnot(None),
            ).distinct().limit(5).all() if origin]
        tenants_data.append({
            "id": t.id,
            "nombre_empresa": t.nombre_empresa,
            "plan_actual": t.plan_actual,
            "estado_suscripcion": t.estado_suscripcion,
            "admin_email": admin_user.email if admin_user else "Sin Admin",
            "admin_nombre": admin_user.nombre if admin_user else None,
            "ultima_conexion": admin_user.ultima_conexion if admin_user else None,
            "sesion_vigente": bool(
                admin_user
                and admin_user.sesion_activa
                and admin_user.ultima_conexion
                and admin_user.ultima_conexion >= limite_sesion
            ),
            "api_configurada": api_configurada,
            "api_en_uso": reservas_api > 0,
            "api_origenes": allowed_origins,
            "reservas_api": reservas_api,
        })
    
    return templates.TemplateResponse("admin_tenants.html", {
        "request": request,
        "tenants": tenants_data,
        "current_user": cred,
        "disable_theme_toggle": True,
    })


@router.get("/tenants/{id_tenant}/facturacion", response_class=HTMLResponse)
def ver_facturacion_tenant(
    id_tenant: str,
    request: Request,
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login),
):
    verificar_superadmin(cred)
    tenant = db.query(models.Tenant).filter(models.Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")

    facturas = []
    error_facturacion = None
    if tenant.stripe_customer_id and stripe_utils.stripe.api_key:
        try:
            resultado = stripe.Invoice.list(customer=tenant.stripe_customer_id, limit=50)
            for factura in resultado.auto_paging_iter():
                fecha = factura.get("created")
                facturas.append({
                    "numero": factura.get("number") or factura.get("id"),
                    "estado": factura.get("status") or "pendiente",
                    "monto": (factura.get("amount_paid") or factura.get("amount_due") or 0) / 100,
                    "moneda": (factura.get("currency") or "clp").upper(),
                    "fecha": datetime.fromtimestamp(fecha) if fecha else None,
                    "url": factura.get("hosted_invoice_url"),
                })
        except stripe.StripeError:
            error_facturacion = "No fue posible consultar las facturas en Stripe."

    return templates.TemplateResponse("admin_tenant_facturacion.html", {
        "request": request,
        "current_user": cred,
        "tenant": tenant,
        "facturas": facturas,
        "error_facturacion": error_facturacion,
    })

@router.post("/tenants/crear")
def crear_tenant(
    id_tenant: str = Form(...),
    nombre_empresa: str = Form(...),
    plan_actual: str = Form("Starter"),
    email_admin: str = Form(...),
    password_admin: str = Form(...),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    if cred.tenant_id != "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de SuperAdmin.")
        
    # Validar si ya existe
    existe = db.query(models.Tenant).filter(models.Tenant.id == id_tenant).first()
    if existe:
        raise HTTPException(status_code=400, detail="El ID del Tenant ya está en uso.")
        
    existe_correo = db.query(models.Usuario).filter(models.Usuario.email == email_admin).first()
    if existe_correo:
        raise HTTPException(status_code=400, detail="El correo del administrador ya está en uso.")
        
    nuevo_tenant = models.Tenant(
        id=id_tenant,
        nombre_empresa=nombre_empresa,
        plan_actual=plan_actual,
        estado_suscripcion="activa"
    )
    db.add(nuevo_tenant)
    db.flush()
    
    from app.core.security import get_password_hash
    nuevo_admin = models.Usuario(
        tenant_id=id_tenant,
        nombre="Administrador",
        email=email_admin,
        password_hash=get_password_hash(password_admin),
        rol="admin"
    )
    db.add(nuevo_admin)
    db.commit()
    
    return RedirectResponse(url="/admin/tenants", status_code=303)

@router.post("/tenants/{id_tenant}/desactivar")
def desactivar_tenant(id_tenant: str, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    if cred.tenant_id != "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de SuperAdmin.")
        
    if id_tenant == "default":
        raise HTTPException(status_code=400, detail="No se puede desactivar la cuenta principal.")
        
    tenant = db.query(models.Tenant).filter(models.Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
        
    tenant.estado_suscripcion = "cancelada"
    db.query(models.Usuario).filter(models.Usuario.tenant_id == id_tenant).update(
        {models.Usuario.sesion_activa: False}, synchronize_session=False
    )
    db.commit()
    
    return RedirectResponse(url="/admin/tenants", status_code=303)


@router.post("/tenants/{id_tenant}/reactivar")
def reactivar_tenant(id_tenant: str, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    verificar_superadmin(cred)
    if id_tenant == "default":
        raise HTTPException(status_code=400, detail="No se puede modificar la cuenta principal.")
    tenant = db.query(models.Tenant).filter(models.Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
    primera_activacion = tenant.estado_suscripcion != "activa"
    tenant.estado_suscripcion = "activa"
    db.commit()
    if primera_activacion:
        _avisar_activacion_interna(db, tenant, "Reactivación manual")
    return RedirectResponse(url="/admin/tenants", status_code=303)

@router.post("/tenants/{id_tenant}/editar-plan")
def editar_plan(
    id_tenant: str, 
    nuevo_plan: str = Form(...), 
    nuevo_estado: str = Form(...), 
    db: Session = Depends(get_db), 
    cred: CurrentUser = Depends(verificar_login)
):
    if cred.tenant_id != "default" or cred.rol != "admin":
        raise HTTPException(status_code=403, detail="Acceso denegado. Se requieren permisos de SuperAdmin.")
        
    tenant = db.query(models.Tenant).filter(models.Tenant.id == id_tenant).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant no encontrado.")
        
    primera_activacion = tenant.estado_suscripcion != "activa" and nuevo_estado == "activa"
    tenant.plan_actual = nuevo_plan
    tenant.estado_suscripcion = nuevo_estado
    db.commit()
    if primera_activacion:
        _avisar_activacion_interna(db, tenant, "Activación manual")
    
    return RedirectResponse(url="/admin/tenants", status_code=303)


# ==========================================
#   RUTA TEMPORAL: CREAR SUPERADMIN
# ==========================================
from app.core.security import get_password_hash

@router.get('/setup-superadmin', response_class=HTMLResponse)
def get_setup_superadmin():
    html = '''
    <html><body style="font-family: sans-serif; padding: 40px; background: #f0f4f8;">
    <div style="max-w-md; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
        <h2>Crear Cuenta SuperAdmin</h2>
        <form action="/admin/setup-superadmin" method="POST">
            <label>Nombre:</label><br>
            <input type="text" name="nombre" required style="width: 100%; padding: 8px; margin-bottom: 15px;"><br>
            <label>Correo Electrónico:</label><br>
            <input type="email" name="email" required style="width: 100%; padding: 8px; margin-bottom: 15px;"><br>
            <label>Contraseña:</label><br>
            <input type="password" name="password" required style="width: 100%; padding: 8px; margin-bottom: 20px;"><br>
            <button type="submit" style="background: #2563eb; color: white; padding: 10px 15px; border: none; border-radius: 5px; cursor: pointer; width: 100%;">Crear Súper Administrador</button>
        </form>
    </div>
    </body></html>
    '''
    return HTMLResponse(content=html)

@router.post('/setup-superadmin')
def post_setup_superadmin(
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # Verificamos si ya existe el correo
    existe = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if existe:
        return HTMLResponse('Error: El correo ya existe en el sistema.')
        
    nuevo_admin = models.Usuario(
        tenant_id='default',
        nombre=nombre,
        email=email,
        password_hash=get_password_hash(password),
        rol='admin'
    )
    db.add(nuevo_admin)
    db.commit()
    
    html_success = '''
    <html><body style="font-family: sans-serif; padding: 40px; background: #f0f4f8; text-align: center;">
    <h2>¡SuperAdmin Creado Exitosamente!</h2>
    <p>Correo: <b>{}</b></p>
    <p>Ya puedes iniciar sesión y verás el panel de Tenants.</p>
    <br>
    <a href="/admin/login" style="background: #10b981; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Ir al Login</a>
    </body></html>
    '''.format(email)
    
    return HTMLResponse(content=html_success)


@router.post("/config/horarios")
async def guardar_config_horarios(cred: CurrentUser = Depends(verificar_login)):
    """Editor antiguo de bloques fijos: los horarios ahora se editan en Configuración del negocio."""
    return RedirectResponse(url="/admin/configuracion-negocio#horarios", status_code=303)
