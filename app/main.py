import sqlite3
from fastapi import FastAPI, Form
from fastapi.responses import RedirectResponse
from app.database import Base, engine
from app.routes import cliente, admin
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import sys
import os
print("DB REAL:", os.path.abspath("agendamientos.db"))
from fastapi.templating import Jinja2Templates
from pathlib import Path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))





app = FastAPI()
templates = Jinja2Templates(directory="app/templates")
@app.post("/admin/actualizar-nota/{id}")
def actualizar_nota(id: int, nota: str = Form(...)):
    conn = sqlite3.connect("agendamientos.db")
    cur = conn.cursor()

    cur.execute("UPDATE agendamientos SET nota_interna=? WHERE id=?", (nota, id))
    conn.commit()
    conn.close()

    # Volver directo al panel
    return RedirectResponse(url="/admin/panel", status_code=303)

BASE_DIR = Path(__file__).resolve().parent 

# Crear tablas en la DB
Base.metadata.create_all(bind=engine)


# Incluir rutas
app.include_router(cliente.router, prefix="/cliente", tags=["Cliente"])
app.include_router(admin.router, prefix="/admin", tags=["Administrador"])

# carpeta para archivos estáticos
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")




