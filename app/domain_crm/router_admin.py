from fastapi import APIRouter, Depends, Request, HTTPException, Query, Form, Body
from sqlalchemy.orm import Session
from pydantic import BaseModel
from sqlalchemy import func
from app.core.database import SessionLocal
from app.core import models, schemas
from typing import List, Optional, Tuple
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
import json
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasicCredentials
import os
from starlette.status import HTTP_303_SEE_OTHER
from datetime import datetime, timedelta, time as dt_time, date as dt_date
import pytz
import sqlite3
import openpyxl
from io import BytesIO 
from app.infrastructure.email_utils import enviar_confirmacion_agendamiento, enviar_correo_cancelacion
from app.domain_agenda.router_cliente import Recursos, calcular_fin_especializado
import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

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
#     SECURITY & JWT
# =============================
from jose import jwt, JWTError
from datetime import datetime, timedelta
from passlib.context import CryptContext
from fastapi import HTTPException, status
from app.core import models

SECRET_KEY = ***REMOVED***
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 día

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


# =============================
#     LOGIN / LOGOUT
# =============================

@router.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    return templates.TemplateResponse("admin_login.html", {"request": request})
    
@router.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    usuario = db.query(models.Usuario).filter(models.Usuario.email == username).first()
    
    if not usuario or not verify_password(password, usuario.password_hash):
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "Correo o contraseña incorrectos"
        })
        
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": usuario.email, "tenant_id": usuario.tenant_id, "rol": usuario.rol},
        expires_delta=access_token_expires
    )
    
    response = RedirectResponse(url="/admin/dashboard", status_code=status.HTTP_303_SEE_OTHER)
    response.set_cookie(key="access_token", value=f"Bearer {access_token}", httponly=True)
    return response


# =============================
#     VERIFICAR LOGIN (SaaS)
# =============================

class CurrentUser:
    def __init__(self, email: str, tenant_id: str, rol: str):
        self.email = email
        self.tenant_id = tenant_id
        self.rol = rol

def verificar_login(request: Request) -> CurrentUser:
    """Verifica el JWT y retorna el contexto Multi-Tenant del usuario."""
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")
        
    token = token.split(" ")[1]
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        tenant_id: str = payload.get("tenant_id")
        rol: str = payload.get("rol")
        
        if email is None or tenant_id is None:
            raise HTTPException(status_code=401, detail="Token inválido")
            
        return CurrentUser(email=email, tenant_id=tenant_id, rol=rol)
        
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")


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
            print(f"  -> Filtrando por fecha: {fecha}")
        except ValueError:
            pass

    agendamientos = query.order_by(models.Agendamiento.id).all()
    print(f"  -> RESULTADO: {len(agendamientos)} agendamientos encontrados")
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


class ReprogramarCitaSchema(BaseModel):
    fecha_inicio: datetime


def verificar_disponibilidad_detalle(
    db: Session, 
    tipo_servicio: str, 
    inicio: datetime, 
    duracion_horas: int, 
    excluir_id: Optional[int] = None
) -> Tuple[bool, str]:
    # 1. Chequear si el día está bloqueado por administración
    dia_bloqueado = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.fecha == inicio.date()).first()
    if dia_bloqueado:
        return False, f"El día {inicio.strftime('%d/%m/%Y')} está bloqueado administrativamente ({dia_bloqueado.motivo or 'Cerrado'})."

    tz_chile = pytz.timezone("America/Santiago")
    if inicio.tzinfo is None:
        inicio = tz_chile.localize(inicio)

    # 2. Calcular fin
    if tipo_servicio == "especializado":
        fin = calcular_fin_especializado(inicio, duracion_horas)
    else:
        fin = inicio + timedelta(hours=duracion_horas)

    h_inicio = inicio.time()
    h_fin = fin.time()
    
    # 3. Horario de atención: 08:00 - 18:00
    if h_inicio < dt_time(8, 0) or h_fin > dt_time(18, 0):
        return False, "La cita debe estar dentro del horario de atención permitido (08:00 - 18:00)."

    # 4. Horario de colación: No cruzar 12:00 a 13:00
    if h_inicio < dt_time(13, 0) and h_fin > dt_time(12, 0):
        return False, "La cita interfiere con el horario de colación obligatorio (12:00 - 13:00)."

    # 5. Validación por tipo de servicio y días
    dia_semana = inicio.weekday() # 0:Lunes, 2:Miércoles...
    hora_str = inicio.strftime("%H:%M")

    if tipo_servicio == "domicilio_taller":
        if duracion_horas != 2:
            return False, "La duración de este tipo de servicio debe ser de 2 horas."
            
        if dia_semana == 2: # Miércoles
            if hora_str not in ["09:00", "13:00"]:
                return False, "Los miércoles los servicios en local/domicilio solo pueden iniciar a las 09:00 o 13:00."
        else:
            if hora_str not in ["09:00", "13:00", "15:30"]:
                return False, "Los servicios en local/domicilio solo pueden iniciar a las 09:00, 13:00 o 15:30."

    elif tipo_servicio == "especializado":
        if dia_semana == 2 and hora_str not in ["09:00", "13:00"]:
            return False, "Los miércoles los servicios especializados solo pueden iniciar a las 09:00 o 13:00."
    else:
        return False, f"Tipo de servicio '{tipo_servicio}' no válido."

    # 6. Validar traslapes/capacidad (excluyendo la misma cita)
    query = db.query(models.Agendamiento).filter(
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio,
        models.Agendamiento.estado != "cancelado"
    )
    if excluir_id is not None:
        query = query.filter(models.Agendamiento.id != excluir_id)
        
    agendados_en_bloque = query.count()
    limite_equipos = len(Recursos.get(tipo_servicio, []))
    
    if agendados_en_bloque >= limite_equipos:
        return False, f"No hay equipos disponibles en este horario (máximo {limite_equipos} citas simultáneas)."

    return True, ""


@router.post("/reprogramar-cita/{id}")
async def reprogramar_cita(
    id: int,
    payload: ReprogramarCitaSchema,
    db: Session = Depends(get_db),
    admin = Depends(verificar_login)
):
    ag = db.query(models.Agendamiento).filter(models.Agendamiento.id == id).first()
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
    
    # Calcular fin
    if ag.tipo_servicio.value == "especializado":
        fin_nueva_naive = calcular_fin_especializado(inicio_nueva_naive, ag.duracion_horas)
    else:
        fin_nueva_naive = inicio_nueva_naive + timedelta(hours=ag.duracion_horas)
        
    # Verificar disponibilidad
    disponible, msg_error = verificar_disponibilidad_detalle(
        db=db,
        tipo_servicio=ag.tipo_servicio.value,
        inicio=inicio_nueva_naive,
        duracion_horas=ag.duracion_horas,
        excluir_id=ag.id
    )
    
    if not disponible:
        return {"status": "error", "message": msg_error}
        
    # Asignar equipo disponible
    equipos_posibles = Recursos.get(ag.tipo_servicio.value, [])
    equipo_asignado = None
    
    # 1. Intentar con el equipo actual
    current_team = ag.equipo
    if current_team in equipos_posibles:
        ocupado = db.query(models.Agendamiento).filter(
            models.Agendamiento.id != ag.id,
            models.Agendamiento.equipo == current_team,
            models.Agendamiento.fecha_inicio < fin_nueva_naive,
            models.Agendamiento.fecha_termino > inicio_nueva_naive,
            models.Agendamiento.estado != "cancelado"
        ).first()
        if not ocupado:
            equipo_asignado = current_team
            
    # 2. Si el actual está ocupado, buscar otro
    if not equipo_asignado:
        for eq in equipos_posibles:
            if eq == current_team:
                continue
            ocupado = db.query(models.Agendamiento).filter(
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
        return {"status": "error", "message": "No se encontró un equipo disponible para este horario."}
        
    # Guardar cambios
    ahora_str = datetime.now(tz_chile).strftime("%H:%M")
    log_reprogramacion = f"\n[REPROGRAMACIÓN {ahora_str}]: {ag.fecha_inicio.strftime('%d/%m %H:%M')} ({ag.equipo}) -> {inicio_nueva_naive.strftime('%d/%m %H:%M')} ({equipo_asignado})"
    
    ag.fecha_inicio = inicio_nueva_naive
    ag.fecha_termino = fin_nueva_naive
    ag.equipo = equipo_asignado
    ag.nota_interna = (ag.nota_interna or "") + log_reprogramacion
    
    try:
        db.commit()
        return {"status": "ok"}
    except Exception as e:
        db.rollback()
        return {"status": "error", "message": f"Error al guardar en base de datos: {str(e)}"}


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
    
    # Capacidad Futura (Mejora 7)
    CAPACIDAD_DIARIA = 8
    def get_capacidad_rango(dias: int):
        fecha_fin = hoy_dt + timedelta(days=dias)
        dias_habiles = sum(1 for i in range(dias) if (hoy_dt + timedelta(days=i)).weekday() != 6)
        capacidad_total = dias_habiles * CAPACIDAD_DIARIA
        ocupado = db.query(models.Agendamiento).filter(
            models.Agendamiento.fecha_inicio >= hoy_dt.replace(tzinfo=None),
            models.Agendamiento.fecha_inicio < fecha_fin.replace(tzinfo=None),
            models.Agendamiento.estado != "cancelado"
        ).count()
        disponible = max(0, capacidad_total - ocupado)
        porcentaje = round((ocupado / capacidad_total) * 100, 1) if capacidad_total > 0 else 0
        estado = "Saturado" if porcentaje > 80 else ("Media" if porcentaje > 50 else "Libre")
        return {"disponible": disponible, "total": capacidad_total, "porcentaje": porcentaje, "estado": estado, "ocupado": ocupado}
        
    capacidad = {
        "d7": get_capacidad_rango(7),
        "d15": get_capacidad_rango(15),
        "d30": get_capacidad_rango(30),
        "d60": get_capacidad_rango(60),
    }

    # Citas por estado
    confirmadas = query.filter(models.Agendamiento.estado == "confirmado").count()
    pendientes = query.filter(models.Agendamiento.estado == "pendiente").count()
    canceladas = query.filter(models.Agendamiento.estado == "cancelado").count()
    
    # Tasa de confirmación
    tasa_confirmacion = 0.0
    if (confirmadas + pendientes) > 0:
        tasa_confirmacion = round((confirmadas / (confirmadas + pendientes)) * 100, 1)
        
    # Distribución por subtipo (Taller/Local vs Domicilio)
    servicios_raw = query.with_entities(
        models.Agendamiento.subtipo,
        func.count(models.Agendamiento.id)
    ).group_by(models.Agendamiento.subtipo).all()
    
    servicios_labels = []
    servicios_valores = []
    for sub, count in servicios_raw:
        label = "🛠️ Local" if sub == "taller" else ("🏠 Domicilio" if sub == "domicilio" else str(sub).capitalize())
        servicios_labels.append(label)
        servicios_valores.append(count)
        
    # Carga de trabajo por equipo (excluyendo cancelados)
    equipos_raw = query.with_entities(
        models.Agendamiento.equipo,
        func.count(models.Agendamiento.id)
    ).filter(models.Agendamiento.estado != "cancelado").group_by(models.Agendamiento.equipo).all()
    
    equipos_labels = [eq if eq else "Sin Equipo" for eq, _ in equipos_raw]
    equipos_valores = [count for _, count in equipos_raw]
    
    # Top 5 marcas de vehículos
    marcas_raw = query.with_entities(
        models.Agendamiento.marca,
        func.count(models.Agendamiento.id)
    ).filter(models.Agendamiento.marca != None).group_by(models.Agendamiento.marca).order_by(func.count(models.Agendamiento.id).desc()).limit(5).all()
    
    marcas_labels = [str(marca).upper().strip() for marca, _ in marcas_raw]
    marcas_valores = [count for _, count in marcas_raw]
    
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
        func.to_char(models.Agendamiento.fecha_inicio, 'YYYY-MM'),
        func.count(models.Agendamiento.id)
    ).group_by(func.to_char(models.Agendamiento.fecha_inicio, 'YYYY-MM')).order_by(func.to_char(models.Agendamiento.fecha_inicio, 'YYYY-MM').asc()).all()
    
    tendencia_labels = [str(mes) for mes, _ in tendencia_raw if mes]
    tendencia_valores = [count for _, count in tendencia_raw if count]

    # Listas recientes para paneles
    lista_confirmadas = query.filter(models.Agendamiento.estado == "confirmado").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()
    lista_pendientes = query.filter(models.Agendamiento.estado == "pendiente").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()
    lista_canceladas = query.filter(models.Agendamiento.estado == "cancelado").order_by(models.Agendamiento.fecha_inicio.desc()).limit(10).all()

    # Top 10 Tareas Urgentes (Mejora 8)
    tareas_activas_list = db.query(models.Tarea).filter(models.Tarea.estado.notin_(["Completada", "Cancelada"])).all()
    
    def puntaje_tarea(t):
        p_score = {"Crítica": 4, "Alta": 3, "Media": 2, "Baja": 1}.get(t.prioridad, 0)
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

    stats = {
        "agendas_hoy": agendas_hoy,
        "agendas_semana": agendas_semana,
        "agendas_mes": agendas_mes,
        "tareas_activas": tareas_activas,
        "tareas_vencidas": tareas_vencidas,
        "capacidad": capacidad,
        "total": total_citas,
        "confirmadas": confirmadas,
        "pendientes": pendientes,
        "canceladas": canceladas,
        "tasa_confirmacion": tasa_confirmacion,
        "servicios_labels": json.dumps(servicios_labels),
        "servicios_valores": json.dumps(servicios_valores),
        "equipos_labels": json.dumps(equipos_labels),
        "equipos_valores": json.dumps(equipos_valores),
        "marcas_labels": json.dumps(marcas_labels),
        "marcas_valores": json.dumps(marcas_valores),
        "utm_stats": utm_stats,
        "tendencia_labels": json.dumps(tendencia_labels),
        "tendencia_valores": json.dumps(tendencia_valores)
    }

    listas = {
        "confirmadas": lista_confirmadas,
        "pendientes": lista_pendientes,
        "canceladas": lista_canceladas,
        "top_tareas": top_tareas
    }

    return templates.TemplateResponse(
        name="admin_dashboard.html",
        context={"request": request, "stats": stats, "listas": listas}
    )