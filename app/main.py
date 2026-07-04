import os
import sys
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
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
from app.domain_ai import router_ai as admin_ai
# IMPORTANTE: Cambiamos el import para usar la función que está en email_utils
from app.infrastructure.email_utils import procesar_flujo_automatico 

# Importaciones del Bot de WhatsApp
from app.infrastructure.webhook import router as webhook_router
from app.infrastructure.confirmation import router as confirmation_router

# Autenticación JWT API
from app.api.routers import auth, tareas

# Configuración de logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = Path(__file__).resolve().parent 

app = FastAPI()

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
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Asegurar que el tenant 'default' exista para evitar IntegrityError
        tenant = db.query(models.Tenant).filter(models.Tenant.id == "default").first()
        if not tenant:
            nuevo_tenant = models.Tenant(
                id="default",
                nombre_empresa="Nexora Default"
            )
            db.add(nuevo_tenant)
            db.commit()
            
        inicializar_campos_sistema(db)
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
    if not scheduler.get_job("recordatorios_test"):
        scheduler.add_job(
            procesar_flujo_automatico,
            'interval',
            minutes=1, 
            id="recordatorios_test",
            replace_existing=True
        )
        scheduler.start()
    
    if not scheduler.running:
        scheduler.start()
        logger.info("🚀 SISTEMA DE PRUEBA INICIADO: Revisión cada 1 minutos activada.")

@app.on_event("shutdown")
def shutdown_event():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 Scheduler apagado correctamente.")

# Registro de rutas
app.include_router(admin.router, prefix="/admin", tags=["Administrador"])
app.include_router(admin_crm.router, tags=["CRM"])
app.include_router(admin_team.router, tags=["Team"])
app.include_router(admin_ai.router, tags=["AI"])
app.include_router(cliente.router, prefix="/cliente", tags=["Cliente"])

# Registro de rutas del Bot de WhatsApp
app.include_router(webhook_router, prefix="/api", tags=["Webhook Twilio"])
app.include_router(confirmation_router, prefix="/api", tags=["Confirmación Web"])

# Autenticación API REST (Nuevo Frontend)
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(tareas.router, prefix="/api/v1/tareas", tags=["Tareas Kanban"])
app.include_router(dashboard.router, prefix="/api/v1/dashboard", tags=["Dashboard API"])

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

@app.on_event("startup")
async def debug_routes():
    print("\n--- RUTAS CARGADAS ---")
    for route in app.routes:
        if hasattr(route, 'path'):
            print(f"Ruta: {route.path}")
    print("----------------------\n")