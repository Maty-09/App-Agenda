from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
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
from app.utils.email_utils import enviar_confirmacion_agendamiento, enviar_correo_cancelacion
from datetime import datetime, timedelta

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
    # Cambia la línea 48 por esto:
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

    print("=" * 80)
    print(f"DEBUG PANEL: subtipo={subtipo}, tipo_servicio={tipo_servicio}, fecha={fecha}")

    if subtipo:
        filter_subtipo = subtipo.lower().strip()
        if filter_subtipo == "local":
            filter_subtipo = "taller"
        query = query.filter(models.Agendamiento.subtipo == filter_subtipo)
        print(f"  → Filtrando por subtipo: {filter_subtipo}")
    if tipo_servicio:
        query = query.filter(models.Agendamiento.tipo_servicio == tipo_servicio)
        print(f"  → Filtrando por tipo_servicio: {tipo_servicio}")
    if fecha:
        try:
            fecha_inicio = datetime.strptime(fecha, "%Y-%m-%d")
            fecha_fin = fecha_inicio + timedelta(days=1)
            query = query.filter(
                models.Agendamiento.fecha_inicio >= fecha_inicio,
                models.Agendamiento.fecha_inicio < fecha_fin
            )
            print(f"  → Filtrando por fecha: {fecha}")
        except ValueError:
            pass

    agendamientos = query.order_by(models.Agendamiento.id).all()
    print(f"  → RESULTADO: {len(agendamientos)} agendamientos encontrados")
    for ag in agendamientos:
        print(f"    - ID {ag.id}: {ag.nombre} {ag.apellido} - {ag.fecha_inicio}")
    print("=" * 80)
    
    utm_registro = db.query(models.UTMRegistro).all()

    dias_bloqueados = db.query(models.DiaBloqueado).all()

    colores = {
        "Equipo Cristhian": "#3F22FF",
        "Equipo Samuel": "#FC4646",
        "Equipo Movil": "#32CD32",
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

    # --- NUEVA LÍNEA 2: Agregamos los bloqueos al calendario ---
    for b in dias_bloqueados:
        eventos_lista.append({
            "id": str(b.id),
            "start": b.fecha.strftime("%Y-%m-%d"), # Solo fecha para que sea todo el día
            "display": "background",              # Pinta el fondo del calendario
            "backgroundColor": "#FFDADA",         # Color rojo suave
            "extendedProps": { "tipo": "bloqueo" } # Identificador para JS
        })

    # Convertimos a string JSON
    eventos_json_str = json.dumps(eventos_lista)

    base_url = str(request.base_url).rstrip("/")
    links_agenda = {
        "Domicilio": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=domicilio",
        "Local": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=local",
        "Especializado": f"{base_url}/cliente/agendar_web?tipo=especializado",
    }

    return templates.TemplateResponse(
        name="admin_agendamientos.html",
        context={
            "request": request,  # Aquí adentro sí va de nuevo si usas 'context='
            "agendamientos": agendamientos,
            "dias_bloqueados": dias_bloqueados,
            "tipo_servicio": tipo_servicio,
            "subtipo": subtipo,
            "eventos_json": eventos_json_str,
            "fecha": fecha,
            "utm_registro": utm_registro,
            "links_agenda": links_agenda
        }
    )


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
        url="/admin/panel",
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
        "local" : {
            "label": "Servicio en Local",
            "url": f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=local"
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
    subtipo: str = "local", # Por defecto local
    db: Session = Depends(get_db)
):
    raw_subtipo = subtipo.lower().strip() if subtipo else "local"
    db_subtipo = "taller" if raw_subtipo == "local" else raw_subtipo

    # Buscamos los campos que coincidan con el subtipo seleccionado
    campos = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.subtipo_servicio == db_subtipo
    ).order_by(models.CampoFormulario.orden.asc()).all()

    return templates.TemplateResponse("admin_config_form.html", {
        "request": request,
        "campos": campos,
        "subtipo_actual": raw_subtipo
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
    raw_subtipo = subtipo_servicio.lower().strip()
    db_subtipo = "taller" if raw_subtipo == "local" else raw_subtipo
    
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
            campo.subtipo_servicio = db_subtipo
            campo.label = texto_label
            campo.tipo_campo = tipo_campo
            campo.opciones = opciones
            campo.obligatorio = obligatorio
            campo.nombre_tecnico = nombre_tecnico
    else:
        nuevo = models.CampoFormulario(
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
async def eliminar_campo(campo_id: int, db: Session = Depends(get_db)):
    # 1. Buscamos el campo en la base de datos
    campo = db.query(models.CampoFormulario).filter(models.CampoFormulario.id == campo_id).first()
    
    if not campo:
        print(f"No se encontró el campo con ID {campo_id}")
        return RedirectResponse(url="/admin/configurar-formulario", status_code=303)

    # Guardamos el subtipo para poder redireccionar al mismo sitio después
    subtipo_servicio = "local" if campo.subtipo_servicio == "taller" else campo.subtipo_servicio

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
    subtipo_redirect = "local" if campo.subtipo_servicio == "taller" else campo.subtipo_servicio
    return RedirectResponse(f"/admin/configurar-formulario?subtipo={subtipo_redirect}", status_code=303)



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

# 1. Definimos la estructura que esperamos recibir del JS
class BloqueoDiaSchema(BaseModel):
    fecha: str
    motivo: Optional[str] = None

@router.post("/bloquear-dia-completo")
def bloquear_dia(datos: BloqueoDiaSchema, db: Session = Depends(get_db)):
    # Ahora accedemos a datos.fecha en lugar de un Form
    try:
        fecha_dt = datetime.strptime(datos.fecha, "%Y-%m-%d").date()
    except ValueError:
        return {"error": "Formato de fecha inválido"}, 400
    
    # Verificamos que no exista ya
    existe = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.fecha == fecha_dt).first()
    
    if not existe:
        nuevo = models.DiaBloqueado(fecha=fecha_dt, motivo=datos.motivo)
        db.add(nuevo)
        db.commit()
    
    
    # Como es una petición AJAX (fetch), es mejor devolver un JSON de éxito 
    # en lugar de un RedirectResponse, para que el JS haga el reload.
    return {"status": "success", "message": "Día bloqueado correctamente"}

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
        raise HTTPException(status_code=400, detail="Formato de fecha inválido")
    
    existe = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.fecha == fecha_dt).first()
    if not existe:
        nuevo = models.DiaBloqueado(fecha=fecha_dt, motivo=motivo)
        db.add(nuevo)
        db.commit()
    
    return RedirectResponse(url="/admin/panel", status_code=303)

@router.post("/desbloquear-dia/{id}") 
def desbloquear_dia(id: int, db: Session = Depends(get_db)):
    dia = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.id == id).first()
    if dia:
        db.delete(dia)
        db.commit()
        print(f"DEBUG: Día {id} desbloqueado con éxito")
        return {"status": "ok", "message": "Día eliminado"} # Cambiamos la redirección por JSON
    
    return {"status": "error", "message": "No se encontró el registro"}, 404


@router.post("/editar-cita/{id}")
async def editar_cita_admin(
    id: int, 
    fecha: str = Form(...), 
    hora: str = Form(...), 
    duracion_horas: int = Form(...), 
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    cita = db.query(models.Agendamiento).filter(models.Agendamiento.id == id).first()
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
        
    try:
        nueva_fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        nueva_fecha_termino = nueva_fecha_inicio + timedelta(hours=duracion_horas)
        
        cita.fecha_inicio = nueva_fecha_inicio
        cita.fecha_termino = nueva_fecha_termino
        cita.duracion_horas = duracion_horas
        
        db.commit()
        print(f"✅ Cita ID {id} modificada con éxito: {nueva_fecha_inicio} ({duracion_horas} hrs)")
    except Exception as e:
        db.rollback()
        print(f"❌ Error al editar cita: {e}")
        raise HTTPException(status_code=500, detail=str(e))
        
    return RedirectResponse(url="/admin/panel", status_code=303)

@router.get("/api/bloqueos")
def obtener_bloqueos_json(db: Session = Depends(get_db)):
    """API que devuelve bloqueos en formato JSON para FullCalendar"""
    import json
    dias_bloqueados = db.query(models.DiaBloqueado).all()
    
    bloqueos = []
    for b in dias_bloqueados:
        bloqueos.append({
            "id": str(b.id),
            "start": b.fecha.strftime("%Y-%m-%d"),
            "display": "background",
            "backgroundColor": "#FFDADA",
            "extendedProps": { "tipo": "bloqueo", "motivo": b.motivo or "Día bloqueado" }
        })
    
    return bloqueos

@router.get("/api/debug/agendamientos")
def debug_agendamientos(db: Session = Depends(get_db)):
    """Endpoint de debugging para ver todos los agendamientos"""
    agendamientos = db.query(models.Agendamiento).all()
    
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
def debug_ultimo_agendamiento(db: Session = Depends(get_db)):
    """Endpoint de debugging para ver el último agendamiento guardado"""
    ultimo = db.query(models.Agendamiento).order_by(models.Agendamiento.id.desc()).first()
    
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
async def agendar_emergencia(request: Request):
    """
    Ruta para el modo sobrecupo. 
    Redirige al agendamiento web ignorando restricciones (si el formulario lo permite).
    """
    # Obtenemos la base de la URL (ej: http://127.0.0.1:8000)
    base_url = str(request.base_url).rstrip("/")
    
    # Redirigimos al agendamiento de local, pero puedes cambiar el 'tipo' 
    # o añadirle un parámetro 'emergencia=true' para tu lógica interna.
    target_url = f"{base_url}/cliente/agendar_web?tipo=domicilio_taller&subtipo=local&modo=emergencia"
    
    print(f"DEBUG: Accediendo a Modo Emergencia -> {target_url}")
    return RedirectResponse(url=target_url)