from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app import models, schemas
from typing import List, Optional
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
from app.utils.email_utils import  enviar_confirmacion_agendamiento

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

    if subtipo:
        query = query.filter(models.Agendamiento.subtipo == subtipo)
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
    utm_registro = db.query(models.UTMRegistro).all()

    colores = {
        "Equipo Israel": "#3F22FF",
        "Equipo Mendez": "#FC4646",
        "Equipo Movil": "#32CD32",
        "Equipo Taller": "#FF8C00",
    }
    
    eventos_lista = []
    for item in agendamientos:
        start_iso = item.fecha_inicio.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = item.fecha_termino.strftime("%Y-%m-%dT%H:%M:%S") if item.fecha_termino else start_iso

        # LIMPIEZA CLAVE: Evita que comillas o saltos de línea rompan el JS
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

    # Convertimos a string JSON
    eventos_json_str = json.dumps(eventos_lista)

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
        "eventos_json": eventos_json_str, # <--- IMPORTANTE: Nombre unificado
        "fecha": fecha,
        "utm_registro": utm_registro,
        "links_agenda": links_agenda,  
    })


@router.post("/actualizar_nota/{id}")
def actualizar_nota(
    id: int, 
    nota: str = Form(...), 
    db: Session = Depends(get_db)
):
    # Buscamos el registro en la DB usando SQLAlchemy
    agendamiento = db.query(models.Agendamiento).filter(models.Agendamiento.id == id).first()
    
    if not agendamiento:
        print(f"Error: No se encontró el agendamiento ID {id}")
        return RedirectResponse("/admin/panel", status_code=303)

    # Actualizamos la nota interna
    agendamiento.nota_interna = nota
    
    try:
        db.commit()
        print(f"Nota del agendamiento {id} actualizada con éxito.")
    except Exception as e:
        db.rollback()
        print(f"Error al guardar: {e}")
    
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
@router.get("/links-agenda")
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
# ==========================================
#   GESTIÓN DE FORMULARIO DINÁMICO
# ==========================================

@router.get("/configurar-formulario")
def configurar_formulario(
    request: Request, 
    subtipo: str = "taller", # Por defecto taller
    db: Session = Depends(get_db)
):
    # Buscamos los campos que coincidan con el subtipo seleccionado
    campos = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.subtipo_servicio == subtipo
    ).order_by(models.CampoFormulario.orden.asc()).all()

    return templates.TemplateResponse("admin_config_form.html", {
        "request": request,
        "campos": campos,
        "subtipo_actual": subtipo
    })
@router.post("/configurar-formulario/guardar")
async def guardar_campo(
    campo_id: Optional[int] = Form(None),
    subtipo_servicio: str = Form(...),
    label: Optional[str] = Form(None), # Permitir que sea None inicialmente
    tipo_campo: str = Form(...),
    opciones: Optional[str] = Form(None),
    obligatorio: bool = Form(False),
    db: Session = Depends(get_db)
):
    # VALIDACIÓN: Si label es None, le damos un valor por defecto para que no explote
    texto_label = label if label else "Campo sin nombre"
    
    # Ahora procesamos el nombre técnico con seguridad
    nombre_tecnico = texto_label.lower().strip().replace(" ", "_")

    # Mapeo inteligente para campos críticos de la tabla Agendamiento
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
        campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id).first()
        if campo:
            campo.label = texto_label
            campo.tipo_campo = tipo_campo
            campo.opciones = opciones
            campo.obligatorio = obligatorio
            campo.nombre_tecnico = nombre_tecnico
    else:
        nuevo = models.CampoFormulario(
            subtipo_servicio=subtipo_servicio,
            label=texto_label,
            nombre_tecnico=nombre_tecnico,
            tipo_campo=tipo_campo,
            opciones=opciones,
            obligatorio=obligatorio
        )
        db.add(nuevo)

    db.commit()
    return RedirectResponse(url=f"/admin/configurar-formulario?subtipo={subtipo_servicio}", status_code=303)

@router.get("/configurar-formulario/eliminar/{campo_id}")
async def eliminar_campo(campo_id: int, db: Session = Depends(get_db)):
    # 1. Buscamos el campo en la base de datos
    campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id).first()
    
    if not campo:
        print(f"No se encontró el campo con ID {campo_id}")
        return RedirectResponse(url="/admin/configurar-formulario", status_code=303)

    # Guardamos el subtipo para poder redireccionar al mismo sitio después
    subtipo_servicio = campo.subtipo_servicio

    # 2. Lo eliminamos
    db.delete(campo)
    db.commit()

    print(f"Campo {campo_id} eliminado correctamente")
    
    # 3. Redirigimos de vuelta a la configuración de ese subtipo
    return RedirectResponse(
        url=f"/admin/configurar-formulario?subtipo={subtipo_servicio}", 
        status_code=303
    )

@router.post("/configurar-formulario/reordenar")
async def reordenar_campos(
    payload: dict = Body(...), 
    db: Session = Depends(get_db)
):
    posiciones = payload.get("posiciones", [])
    
    try:
        for item in posiciones:
            # Buscamos el campo por su ID
            campo = db.query(models.CampoFormulario).filter(
                models.CampoFormulario.id == int(item['id'])
            ).first()
            
            if campo:
                campo.orden = item['orden']
        
        db.commit()
        return {"status": "success", "message": "Orden actualizado"}
    
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": str(e)}, 500



@router.post("/configurar-formulario/editar/{campo_id}")
def editar_campo(
    campo_id: int,
    label: str = Form(...),
    tipo_campo: str = Form(...),
    opciones: str = Form(None),
    obligatorio: str = Form(None),
    db: Session = Depends(get_db),
    cred: HTTPBasicCredentials = Depends(verificar_login)
):
    campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id).first()
    if not campo:
        return RedirectResponse("/admin/editor-visual-formulario", status_code=303)

    campo.label = label
    campo.tipo_campo = tipo_campo
    campo.opciones = opciones
    campo.obligatorio = True if obligatorio == "on" else False

    db.commit()
    return RedirectResponse(f"/admin/configurar-formulario?subtipo={campo.subtipo_servicio}", status_code=303)



@router.post("/reubicar-emergencia/{id}")
async def reubicar_emergencia(
    id: int, 
    payload: dict = Body(...), 
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    nueva_direccion = payload.get("nueva_direccion")
    ag = db.query(models.Agendamiento).filter(models.Agendamiento.id == id).first()
    
    if not ag:
        return {"status": "error", "message": "No encontrado"}

    ahora = datetime.now().strftime("%H:%M")
    log = f"\n[REUBICACIÓN {ahora}]: {ag.direccion} -> {nueva_direccion}"
    
    ag.direccion = nueva_direccion
    ag.nota_interna = (ag.nota_interna or "") + log
    # Guardamos una marca de modificación para el estilo visual
    ag.modificado = True 
    
    db.commit()
    return {"status": "ok"}