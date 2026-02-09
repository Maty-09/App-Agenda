from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app import models, schemas
from typing import List
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import json
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasicCredentials
import os
from starlette.status import HTTP_303_SEE_OTHER
from datetime import datetime, timedelta
import sqlite3
import openpyxl
from io import BytesIO 
from app.utils.email_utils import enviar_correo_cancelacion, enviar_correo_confirmacion

# Templates
templates = Jinja2Templates(directory="templates")

router = APIRouter()

# Configuración login admin
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "1234")


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
#     LOGIN / LOGOUT
# =============================

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})


@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == ADMIN_USER and password == ADMIN_PASS:
        response = RedirectResponse(url="/admin/panel", status_code=HTTP_303_SEE_OTHER)
        response.set_cookie(key="admin_session", value="valid")
        return response

    return templates.TemplateResponse("admin_login.html", {
        "request": request,
        "error": "Credenciales inválidas"
    })


# =============================
#     VERIFICAR LOGIN
# =============================

def verificar_login(request: Request) -> HTTPBasicCredentials:
    """
    Esta función DEBE retornar ALGO, no None.
    Antes no retornaba nada → FastAPI rompía e insertaba 'undefined' en JS.
    """
    if request.cookies.get("admin_session") != "valid":
        # Esto se ejecuta ANTES de entrar al endpoint
        raise HTTPException(status_code=401, detail="No autorizado")

    # FastAPI exige retornar un valor para que la dependencia sea válida
    return HTTPBasicCredentials(username="admin", password="***")


# =============================
#   ENDPOINTS DE ADMIN
# =============================

@router.get("/agendamientos", response_model=List[schemas.AgendamientoOut])
def listar_agendamientos(db: Session = Depends(get_db)):
    return db.query(models.Agendamiento).order_by(models.Agendamiento.fecha_inicio).all()


@router.get("/panel", response_class=HTMLResponse)
def panel_agendamientos(
    request: Request,
    tipo_servicio: str = Query(None),
    subtipo: str = Query(None),
    fecha: str = Query(None),
    db: Session = Depends(get_db),
    cred: HTTPBasicCredentials = Depends(verificar_login)
):
    
    query = db.query(models.Agendamiento)
    utm_registro = db.query(models.UTMRegistro).all()

    if subtipo:
        query = query.filter(models.Agendamiento.subtipo == subtipo)

    # filtro tipo
    if tipo_servicio:
        query = query.filter(models.Agendamiento.tipo_servicio == tipo_servicio)

    # filtro fecha
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

    eventos = []

    colores = {
        "Equipo Israel": "#3F22FF",
        "Equipo Mendez": "#FC4646",
        "Equipo Movil": "#32CD32",
        "Equipo Taller": "#FF8C00",
    }

    for item in agendamientos:
        #colores = colores.get(item.equipo.upper(), "#8A2BE2") 

        color_equipo = colores.get(item.equipo, "#6c63ff")
        eventos.append({
        "id": item.id,
        "title": f"{item.nombre} {item.apellido}",
        "start": item.fecha_inicio.strftime("%Y-%m-%dT%H:%M:%S"),
        "end": item.fecha_termino.strftime("%Y-%m-%dT%H:%M:%S"),
        "backgroundColor": color_equipo,
        "borderColor": color_equipo,

        # ✅ TODO LO EXTRA VA AQUÍ
        "extendedProps": {
            "tipo": item.tipo_servicio,
            "subtipo": item.subtipo,
            "patente": item.patente,
            "nombre": item.nombre,
            "apellido": item.apellido,
            "telefono": item.telefono,
            "correo": item.correo,
            "direccion": item.direccion,
            "marca": item.marca,
            "modelo": item.modelo,
            "equipo": item.equipo,
            "utm_link": item.utm_link,
        }
        })

    # Convertir eventos a JSON
    eventos_json = json.dumps(eventos)

    # print("\n=== EVENTOS PARA EL CALENDARIO ===")
    # print(eventos_json)
    # print("===================================\n")
    base_url = str(request.base_url).rstrip("/")

    links_agenda = {
        "Domicilio": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=domicilio",
        "Taller": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=taller",
        "Especializado": f"{base_url}/cliente/agendar_web?tipo=especializado",
    }

    return templates.TemplateResponse("admin_agendamientos.html", {
        "request": request,
        "agendamientos": agendamientos,
        "tipo_servicio": tipo_servicio,
        "subtipo": subtipo,
        "eventos": eventos_json,
        "fecha": fecha,
        "utm_registro": utm_registro,
        "links_agenda": links_agenda,  
    })

@router.post("/admin/actualizar_nota/{id}")
def actualizar_nota(id: int, nota: str = Form(...)):
    conn = sqlite3.connect("agendaminetos.db")
    cur = conn.cursor()

    cur.execute("UPDATE agendamientos SET nota_interna = ? WHERE id = ?", (nota, id))
    conn.commit()
    conn.close()
    
    return RedirectResponse("/admin/panel", status_code=303)


# =============================
# Exportacion UTM
# ============================

@router.get("/export/utm")
def export_utm(
    db: Session = Depends(get_db),
    cred: HTTPBasicCredentials = Depends(verificar_login)
):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Agendamientos UTM"
    
    ws.append(["ID","Origen Link", "Canal","Creado Por","RUT","Nombre","Apellido","Direccion","Patente","Marca","Modelo","Fecha Inicio","Fecha Termino"])

    agendamientos = db.query(models.Agendamiento).order_by(models.Agendamiento.fecha_inicio.desc()).all()
    
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
        models.Agendamiento.id == id
    ).first()

    if not ag:
        raise HTTPException(404, "Agendamiento no encontrado")

    ag.estado = "cancelado"
    db.commit()
    db.refresh(ag)

    enviar_correo_cancelacion(ag)

    return RedirectResponse(
        url="/admin/agendamientos",
        status_code=303
    )


# ENVIAR LINKS POR ADMIN
@router.get("/admin/links-agenda")
def obtener_links_agenda(request: Request, admin = Depends(verificar_login)):
    base_url = str(request.base_url).rstrip("/")

    links = {
        "domicilio": {
            "label": "Servicio a Domicilio",
            "url": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=domicilio"
            },
        "taller" : {
            "label": "Sevicio en Taller",
            "url": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=taller"
            },
        "especializado" : {
            "label": "Equipo Especializado",
            2: f"{base_url}/cliente/agendar_web?tipo=especializado&duracion_horas=2",
            3: f"{base_url}/cliente/agendar_web?tipo=especializado&duracion_horas=3",
            4: f"{base_url}/cliente/agendar_web?tipo=especializado&duracion_horas=4",
        } 
    }

    return links
