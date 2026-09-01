import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse
from jose import jwt, JWTError
from app.core.security import SECRET_KEY, ALGORITHM
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import pytz
# Importaciones del Scheduler
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger # Cambiamos a Interval para la prueba

# Importaciones locales
from app.core.database import SessionLocal, engine, Base
from app.core import models
from app.domain_agenda import router_cliente as cliente
from app.domain_crm import router_admin as admin
from app.domain_crm import router_clientes as admin_crm
from app.domain_team import router_team as admin_team
# IMPORTANTE: Cambiamos el import para usar la función que está en email_utils
from app.infrastructure.email_utils import procesar_flujo_automatico 

# Importaciones del Bot de WhatsApp
from app.infrastructure.webhook import router as webhook_router
from app.infrastructure.confirmation import router as confirmation_router

# Autenticación JWT API
from app.api.routers import auth, tareas, dashboard, suscripcion, notificaciones, public_agenda, public_booking

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = Path(__file__).resolve().parent 

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def bloquear_prueba_vencida(request: Request, call_next):
    """Mantiene disponible el acceso a suscripción cuando una prueba termina."""
    path = request.url.path
    rutas_permitidas = {"/admin/login", "/admin/logout", "/admin/forgot-password", "/admin/reset-password", "/admin/prueba", "/admin/suscripcion", "/admin/suscripcion/checkout", "/admin/configuracion-inicial", "/admin/onboarding", "/admin/onboarding/finalizar"}
    if path.startswith("/admin") and path not in rutas_permitidas:
        token = request.cookies.get("access_token", "")
        if token.startswith("Bearer "):
            try:
                payload = jwt.decode(token.split(" ", 1)[1], SECRET_KEY, algorithms=[ALGORITHM])
                tenant_id = payload.get("tenant_id")
                if tenant_id:
                    db = SessionLocal()
                    try:
                        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
                        if tenant and tenant.estado_suscripcion == "prueba" and tenant.trial_fin and tenant.trial_fin < models.get_now_chile():
                            return RedirectResponse(url="/admin/suscripcion", status_code=303)
                    finally:
                        db.close()
            except JWTError:
                pass
    return await call_next(request)
# --- CONFIGURACIÓN DEL SCHEDULER ---
scheduler = BackgroundScheduler(timezone="America/Santiago")




def obtener_fecha_minima_habil():
    # Configuramos la hora de Chile
    tz = pytz.timezone('America/Santiago')
    ahora = datetime.now(tz)
    
    contar_horas = 0
    fecha_chequeo = ahora
    
    # Este bucle suma horas una a una, saltando fines de semana
    while contar_horas < 48:
        fecha_chequeo += timedelta(hours=1)
        # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
        if fecha_chequeo.weekday() < 5: 
            contar_horas += 1
            
    return fecha_chequeo

def inicializar_campos_sistema(db: Session):
    existe = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.es_sistema == True
    ).first()
    
    if existe:
        return

    campos_base = [
        {"label": "RUT", "tec": "rut", "ord": 1},
        {"label": "Nombre", "tec": "nombre", "ord": 2},
        {"label": "Apellido", "tec": "apellido", "ord": 3},
        {"label": "Teléfono", "tec": "telefono", "ord": 4},
        {"label": "Marca", "tec": "marca", "ord": 5},
        {"label": "Modelo", "tec": "modelo", "ord": 6},
        {"label": "Patente", "tec": "patente", "ord": 7},
        {"label": "Kilometraje", "tec": "kilometraje", "ord": 8},
    ]

    for c in campos_base:
        for sub in ["taller", "domicilio"]:
            nuevo = models.CampoFormulario(
                label=c["label"],
                nombre_tecnico=c["tec"],
                tipo_campo="text",
                es_sistema=True,
                orden=c["ord"],
                subtipo_servicio=sub,
                obligatorio=True,
                activo=True
            )
            db.add(nuevo)
    db.commit()
    print("✅ Campos base inicializados.")

# --- EVENTOS DE CICLO DE VIDA ---

@app.on_event("startup")
async def startup_event():
    if os.environ.get("VERCEL") == "1":
        logger.info("Entorno Vercel: esquema gestionado por Alembic y scheduler deshabilitado.")
        return

    # Desarrollo local: conserva la compatibilidad con instalaciones antiguas.
    # Producción nunca ejecuta DDL durante un cold start.
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Asegurar que el tenant 'default' exista para evitar IntegrityError
        tenant = db.query(models.Tenant).filter(models.Tenant.id == "default").first()
        if not tenant:
            nuevo_tenant = models.Tenant(
                id="default",
                nombre_empresa="Norem Default"
            )
            db.add(nuevo_tenant)
            db.commit()
            
        inicializar_campos_sistema(db)
        
        # Inicializar datos demo si no existen
        try:
            from scripts.seed_demo import seed_demo
            seed_demo()
        except Exception as e_demo:
            logger.warning(f"Error sembrando datos demo: {e_demo}")
    finally:
        db.close()

    # --- MIGRACIÓN SEGURA: agregar columna boton_enviado si no existe ---
    try:
        from sqlalchemy import text
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE agendamientos ADD COLUMN boton_enviado BOOLEAN DEFAULT 0"))
        logger.info("✅ Migración: columna 'boton_enviado' agregada.")
    except Exception:
        pass  # La columna ya existe, no hacer nada

    # --- CONFIGURACIÓN DE PRUEBA (Cada 10 minutos) ---
    if os.environ.get("VERCEL") != "1":
        if not scheduler.get_job("recordatorios_test"):
            scheduler.add_job(
                procesar_flujo_automatico,
                'interval',
                minutes=1, 
                id="recordatorios_test",
                replace_existing=True
            )
        
        if not scheduler.running:
            scheduler.start()
            logger.info("🚀 SISTEMA DE PRUEBA INICIADO: Revisión cada 1 minutos activada.")
    else:
        logger.info("⚡ Entorno Vercel detectado: BackgroundScheduler deshabilitado por completo.")

@app.on_event("shutdown")
def shutdown_event():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 Scheduler apagado correctamente.")

# Registro de rutas
app.include_router(admin.router, prefix="/admin", tags=["Administrador"])
app.include_router(admin_crm.router, tags=["CRM"])
app.include_router(admin_team.router, tags=["Team"])
app.include_router(cliente.router, prefix="/cliente", tags=["Cliente"])

# Registro de rutas del Bot de WhatsApp
app.include_router(webhook_router, prefix="/api", tags=["Webhook Twilio"])
app.include_router(confirmation_router, prefix="/api", tags=["Confirmación Web"])

# Autenticación API REST (Nuevo Frontend)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(tareas.router, prefix="/api/v1/tareas", tags=["Tareas Kanban"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard API"])
app.include_router(suscripcion.router, prefix="/api/v1/suscripcion", tags=["Monetización SaaS"])
app.include_router(notificaciones.router, prefix="/api/v1", tags=["Notificaciones"])
app.include_router(public_agenda.router, prefix="/api/v1/public", tags=["Agenda pública"])
app.include_router(public_booking.public_router, prefix="/api/public/v1", tags=["API pública"])
app.include_router(public_booking.admin_router, prefix="/api/v1/public-api", tags=["Configuración API pública"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.get("/")
def read_root(request: Request):
    host = request.headers.get("host", "").split(":")[0].lower()
    if host == "agenda.norem.cl":
        return RedirectResponse(url="/admin/login", status_code=307)
    return templates.TemplateResponse("landing.html", {"request": request})

@app.on_event("startup")
async def debug_routes():
    print("\n--- RUTAS CARGADAS ---")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"Ruta: {route.path}")
    print("----------------------\n")
