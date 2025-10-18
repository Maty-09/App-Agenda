from fastapi import APIRouter, Depends,Request,HTTPException, Query, Form
from sqlalchemy.orm import Session
from sqlalchemy import cast,Date
from app.database import SessionLocal, get_db
from app import models, schemas
from typing import List
from fastapi.responses import HTMLResponse,RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials, OAuth2PasswordBearer
import secrets
from starlette.status import HTTP_303_SEE_OTHER
import os
from fastapi.templating import Jinja2Templates
from datetime import datetime, timedelta

templates = Jinja2Templates(directory="templates")

# PRueba

security = OAuth2PasswordBearer(tokenUrl="token")
router = APIRouter()

# Usuario y clave para admin (puedes usar variables de entornos)
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "1234")

# Variable simple para sesión (en producción usar OAuth o JWT)
admin_sessions = set()


# Dependency para obtener sesión de la base de datos prueba
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        response = RedirectResponse(url="/admin/panel", status_code=HTTP_303_SEE_OTHER)
        # Guarda la sesión en cookie (básico, no seguro)
        response.set_cookie(key="admin_session", value="valid")
        return response
    return templates.TemplateResponse("admin_login.html", {"request": request, "error": "Credenciales inválidas"})

def verificar_login(request: Request):
    if request.cookies.get("admin_session") != "valid":
        return RedirectResponse(url="/admin/login", status_code=302)


@router.get("/agendamientos", response_model=List[schemas.AgendamientoOut])
def listar_agendamientos(db: Session = Depends(get_db)):
    return db.query(models.Agendamiento).order_by(models.Agendamiento.fecha_inicio).all()


@router.get("/panel", response_class=HTMLResponse)
def panel_agendamientos(
    request: Request,
    tipo_servicio: str = Query(None),
    fecha: str = Query(None),
    db: Session = Depends(get_db),
    credentials: HTTPBasicCredentials = Depends(verificar_login)
):
    query = db.query(models.Agendamiento)

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

    return templates.TemplateResponse("admin_agendamientos.html", {
        "request": request,
        "agendamientos": agendamientos,
        "tipo_servicio": tipo_servicio,
        "fecha": fecha
    })

@router.post("/eliminar/{id}")
def eliminar_agendamiento(id: int, db: Session = Depends(get_db),
                          credentials: HTTPBasicCredentials = Depends(verificar_login)):
    agendamiento = db.query(models.Agendamiento).get(id)
    if not agendamiento:
        raise HTTPException(status_code=404, detail="No encontrado")
    db.delete(agendamiento)
    db.commit()
    return RedirectResponse("/admin/panel", status_code=303)