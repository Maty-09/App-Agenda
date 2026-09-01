"""API pública para embeber la agenda de un tenant en sitios externos."""

import json
import logging
import math
import secrets
from collections import defaultdict, deque
from datetime import date, datetime, time, timedelta
from threading import Lock
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.api import deps
from app.core import models
from app.domain_agenda.router_cliente import Recursos, obtener_horas_disponibles

public_router = APIRouter()
admin_router = APIRouter()
logger = logging.getLogger(__name__)

PUBLIC_KEY_HEADER = "X-Norem-Public-Key"
PUBLIC_API_CONFIG_KEY = "public_api"
BOOKING_LIMIT = 10
BOOKING_WINDOW_SECONDS = 15 * 60
_booking_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_booking_attempts_lock = Lock()


class PublicApiSettingsIn(BaseModel):
    enabled: bool = False
    allowed_origins: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("allowed_origins")
    @classmethod
    def validate_origins(cls, origins: list[str]) -> list[str]:
        normalized: list[str] = []
        for origin in origins:
            value = origin.strip().rstrip("/")
            if value and not value.startswith(("https://", "http://")):
                value = f"https://{value}"
            if not value:
                raise ValueError("Ingresa un dominio válido")
            if value not in normalized:
                normalized.append(value)
        return normalized


class PublicApiSettingsOut(BaseModel):
    enabled: bool
    allowed_origins: list[str]
    public_key: str | None = None
    availability_url: str | None = None
    booking_url: str | None = None


class PublicBookingIn(BaseModel):
    rut: Annotated[str, Field(min_length=3, max_length=30)]
    nombre: Annotated[str, Field(min_length=1, max_length=120)]
    apellido: Annotated[str, Field(min_length=1, max_length=120)]
    correo: EmailStr
    telefono: Annotated[str, Field(min_length=5, max_length=40)]
    fecha: date
    hora: time
    duracion_minutos: Annotated[int | None, Field(default=None, ge=15, le=480)] = None
    # Compatibilidad temporal para integraciones existentes. Prefiere duracion_minutos.
    duracion_horas: Annotated[float | None, Field(default=None, ge=0.25, le=8)] = None
    tipo_servicio: str = "domicilio_taller"
    subtipo: str = "local"
    direccion: str | None = Field(default=None, max_length=300)
    tipo_vivienda: str = Field(default="No especificado", max_length=120)
    marca: str = Field(default="N/A", max_length=100)
    modelo: str = Field(default="N/A", max_length=100)
    patente: str = Field(default="S/P", max_length=30)
    kilometraje: int | None = Field(default=None, ge=0, le=2_000_000)

    @field_validator("hora")
    @classmethod
    def require_whole_minutes(cls, value: time) -> time:
        if value.second or value.microsecond:
            raise ValueError("La hora debe estar expresada en minutos exactos")
        return value


class PublicBookingOut(BaseModel):
    id: int
    estado: str
    fecha_inicio: datetime
    fecha_termino: datetime


def _tenant_config(tenant: models.Tenant) -> dict:
    try:
        return json.loads(tenant.config_json or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}


def _public_config(tenant: models.Tenant) -> dict:
    config = _tenant_config(tenant)
    public = config.get(PUBLIC_API_CONFIG_KEY, {})
    return public if isinstance(public, dict) else {}


def _duracion_minutos(tenant: models.Tenant, minutos: int | None, horas: float | None) -> int:
    if minutos is not None:
        return minutos
    if horas is not None:
        return max(15, min(480, round(horas * 60)))
    config = _tenant_config(tenant)
    return max(15, min(480, int(config.get("negocio", {}).get("duracion_minutos", 60))))


def _save_public_config(tenant: models.Tenant, public: dict) -> None:
    config = _tenant_config(tenant)
    config[PUBLIC_API_CONFIG_KEY] = public
    tenant.config_json = json.dumps(config)


def _get_tenant_or_404(db: Session, tenant_id: str) -> models.Tenant:
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Empresa no encontrada")
    return tenant


def _cors_headers(request: Request, public: dict) -> dict[str, str]:
    origin = request.headers.get("origin")
    allowed = public.get("allowed_origins", [])
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="Origen no autorizado para esta agenda")
    if not origin:
        return {}
    return {
        "Access-Control-Allow-Origin": origin,
        "Vary": "Origin",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": f"Content-Type, {PUBLIC_KEY_HEADER}",
        "Access-Control-Max-Age": "600",
    }


def _validate_public_access(request: Request, tenant: models.Tenant) -> tuple[dict, dict[str, str]]:
    public = _public_config(tenant)
    if not public.get("enabled"):
        raise HTTPException(status_code=404, detail="La agenda pública no está habilitada")
    provided_key = request.headers.get(PUBLIC_KEY_HEADER)
    expected_key = public.get("public_key")
    if not expected_key or not provided_key or not secrets.compare_digest(provided_key, expected_key):
        raise HTTPException(status_code=401, detail="Clave pública inválida")
    return public, _cors_headers(request, public)


def _enforce_booking_rate_limit(request: Request, tenant_id: str) -> None:
    client_ip = request.client.host if request.client else "unknown"
    key = f"{tenant_id}:{client_ip}"
    now = datetime.utcnow()
    with _booking_attempts_lock:
        attempts = _booking_attempts[key]
        cutoff = now - timedelta(seconds=BOOKING_WINDOW_SECONDS)
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        if len(attempts) >= BOOKING_LIMIT:
            raise HTTPException(
                status_code=429,
                detail="Demasiadas solicitudes. Intenta nuevamente en unos minutos.",
            )
        attempts.append(now)


def _settings_response(request: Request, tenant: models.Tenant, public: dict) -> PublicApiSettingsOut:
    base_url = str(request.base_url).rstrip("/")
    tenant_url = f"{base_url}/api/public/v1/{tenant.id}"
    return PublicApiSettingsOut(
        enabled=bool(public.get("enabled")),
        allowed_origins=public.get("allowed_origins", []),
        public_key=public.get("public_key"),
        availability_url=f"{tenant_url}/availability",
        booking_url=f"{tenant_url}/bookings",
    )


def _require_tenant_admin(current_user: models.Usuario) -> None:
    if current_user.rol not in {"admin", "admin_empresa", "superadmin"}:
        raise HTTPException(status_code=403, detail="Solo un administrador puede configurar la API pública")


@admin_router.get("/settings", response_model=PublicApiSettingsOut)
def get_settings(
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user),
):
    _require_tenant_admin(current_user)
    tenant = _get_tenant_or_404(db, current_user.tenant_id)
    return _settings_response(request, tenant, _public_config(tenant))


@admin_router.put("/settings", response_model=PublicApiSettingsOut)
def update_settings(
    settings: PublicApiSettingsIn,
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user),
):
    _require_tenant_admin(current_user)
    if settings.enabled and not settings.allowed_origins:
        raise HTTPException(status_code=422, detail="Configura al menos un origen permitido antes de habilitar la API")
    tenant = _get_tenant_or_404(db, current_user.tenant_id)
    current = _public_config(tenant)
    public = {
        "enabled": settings.enabled,
        "allowed_origins": settings.allowed_origins,
        "public_key": current.get("public_key") or secrets.token_urlsafe(32),
    }
    _save_public_config(tenant, public)
    db.commit()
    db.refresh(tenant)
    return _settings_response(request, tenant, public)


@admin_router.post("/settings/regenerate-key", response_model=PublicApiSettingsOut)
def regenerate_public_key(
    request: Request,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user),
):
    _require_tenant_admin(current_user)
    tenant = _get_tenant_or_404(db, current_user.tenant_id)
    public = _public_config(tenant)
    public["public_key"] = secrets.token_urlsafe(32)
    public.setdefault("enabled", False)
    public.setdefault("allowed_origins", [])
    _save_public_config(tenant, public)
    db.commit()
    db.refresh(tenant)
    return _settings_response(request, tenant, public)


@public_router.options("/{tenant_id}/{resource:path}", status_code=status.HTTP_204_NO_CONTENT)
def public_preflight(tenant_id: str, resource: str, request: Request, db: Session = Depends(deps.get_db)):
    tenant = _get_tenant_or_404(db, tenant_id)
    public = _public_config(tenant)
    if not public.get("enabled"):
        raise HTTPException(status_code=404, detail="La agenda pública no está habilitada")
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers=_cors_headers(request, public))


@public_router.get("/{tenant_id}/availability")
def get_availability(
    tenant_id: str,
    request: Request,
    fecha: date,
    duracion_minutos: Annotated[int | None, Field(default=None, ge=15, le=480)] = None,
    duracion_horas: Annotated[float | None, Field(default=None, ge=0.25, le=8)] = None,
    tipo_servicio: str = "domicilio_taller",
    db: Session = Depends(deps.get_db),
):
    tenant = _get_tenant_or_404(db, tenant_id)
    _, headers = _validate_public_access(request, tenant)
    if tipo_servicio not in Recursos:
        raise HTTPException(status_code=422, detail="Tipo de servicio no disponible")
    minutos = _duracion_minutos(tenant, duracion_minutos, duracion_horas)
    hours = obtener_horas_disponibles(tipo_servicio, fecha, minutos / 60, db, tenant_id)
    return Response(
        content=json.dumps({"fecha": fecha.isoformat(), "horas": hours}),
        media_type="application/json",
        headers=headers,
    )


@public_router.post("/{tenant_id}/bookings", response_model=PublicBookingOut, status_code=status.HTTP_201_CREATED)
def create_public_booking(
    tenant_id: str,
    payload: PublicBookingIn,
    request: Request,
    response: Response,
    db: Session = Depends(deps.get_db),
):
    tenant = _get_tenant_or_404(db, tenant_id)
    _, headers = _validate_public_access(request, tenant)
    _enforce_booking_rate_limit(request, tenant_id)

    if payload.tipo_servicio not in Recursos:
        raise HTTPException(status_code=422, detail="Tipo de servicio no disponible")
    minutos = _duracion_minutos(tenant, payload.duracion_minutos, payload.duracion_horas)
    duracion_horas = minutos / 60
    slot = payload.hora.strftime("%H:%M")
    available = obtener_horas_disponibles(
        payload.tipo_servicio, payload.fecha, duracion_horas, db, tenant_id
    )
    if slot not in available:
        raise HTTPException(status_code=409, detail="El horario ya no está disponible")

    starts_at = datetime.combine(payload.fecha, payload.hora)
    ends_at = starts_at + timedelta(minutes=minutos)
    assigned_team = None
    for team in Recursos[payload.tipo_servicio]:
        occupied = db.query(models.Agendamiento).filter(
            models.Agendamiento.tenant_id == tenant_id,
            models.Agendamiento.equipo == team,
            models.Agendamiento.fecha_inicio < ends_at,
            models.Agendamiento.fecha_termino > starts_at,
            models.Agendamiento.estado != "cancelado",
        ).first()
        if not occupied:
            assigned_team = team
            break
    if not assigned_team:
        raise HTTPException(status_code=409, detail="El horario ya no está disponible")

    client = db.query(models.Cliente).filter(
        models.Cliente.tenant_id == tenant_id,
        models.Cliente.rut == payload.rut,
    ).first()
    if not client:
        client = models.Cliente(
            tenant_id=tenant_id,
            rut=payload.rut,
            nombre=payload.nombre,
            apellido=payload.apellido,
            correo=str(payload.correo),
            telefono=payload.telefono,
            etiquetas=json.dumps(["API pública"]),
        )
        db.add(client)
        db.flush()
    else:
        client.nombre, client.apellido = payload.nombre, payload.apellido
        client.correo, client.telefono = str(payload.correo), payload.telefono

    booking = models.Agendamiento(
        tenant_id=tenant_id,
        cliente_id=client.id,
        rut=payload.rut,
        nombre=payload.nombre,
        apellido=payload.apellido,
        correo=str(payload.correo),
        telefono=payload.telefono,
        tipo_servicio=payload.tipo_servicio,
        subtipo="taller" if payload.subtipo == "local" else payload.subtipo,
        direccion=payload.direccion,
        tipo_vivienda=payload.tipo_vivienda,
        marca=payload.marca,
        modelo=payload.modelo,
        patente=payload.patente.upper(),
        kilometraje=payload.kilometraje,
        equipo=assigned_team,
        fecha_inicio=starts_at,
        fecha_termino=ends_at,
        # Columna legacy entera; las fechas contienen la duración real en minutos.
        duracion_horas=max(1, math.ceil(minutos / 60)),
        estado="pendiente",
        nota_interna="Reserva creada desde API pública",
    )
    db.add(booking)
    db.flush()
    db.add(models.TimelineEvent(
        tenant_id=tenant_id,
        cliente_id=client.id,
        tipo_evento="RESERVA",
        metadata_json=json.dumps({"agendamiento_id": booking.id, "origen": "API pública"}),
    ))
    db.commit()
    db.refresh(booking)
    for key, value in headers.items():
        response.headers[key] = value
    return booking
