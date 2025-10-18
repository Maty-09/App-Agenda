from fastapi import FastAPI
from app.database import Base, engine
from app.routes import cliente, admin
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sys
import os
from fastapi.templating import Jinja2Templates
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))




app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


# Crear tablas en la DB
Base.metadata.create_all(bind=engine)

# Incluir rutas
app.include_router(cliente.router, prefix="/cliente", tags=["Cliente"])
app.include_router(admin.router, prefix="/admin", tags=["Administrador"])
# carpeta para archivos estáticos
app.mount("/static", StaticFiles(directory="static"), name="static")




