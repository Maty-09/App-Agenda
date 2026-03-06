from fastapi import APIRouter, Depends, HTTPException,Request, Form, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal , get_db
from app.utils.email_utils import (
    enviar_confirmacion_agendamiento, 
    enviar_aviso_accion_al_dueno,  # <--- Nuevo nombre
    enviar_solicitud_confirmacion,
    enviar_aviso_recibido_cliente
)
from app.utils.generar_utm import generar_utm 
from app import models
from sqlalchemy import func
import pytz


# pruebas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()

templates = Jinja2Templates(directory="templates")


@router.get("/agendar_web", response_class=HTMLResponse)
def agendar_web(
    request: Request,
    tipo: str = Query(None),
    subtipo: str = Query(None),
    fecha: str = Query(None),
    hora: str = Query(None),
    duracion_horas: int = Query(None),
    db: Session = Depends(get_db)
):
    # 1. NORMALIZACIÓN Y VALIDACIÓN INICIAL
    tipo = tipo.lower().strip() if tipo else "domicilio_taller"
    subtipo = subtipo.lower().strip() if subtipo else "taller"

    if tipo not in ["especializado", "domicilio_taller"]:
        return RedirectResponse(url="/cliente/agendar_web?tipo=domicilio_taller", status_code=302)

    # 2. OBTENER CAMPOS DINÁMICOS (Lo que configuraste en el Admin)
    # Filtramos por el subtipo para que si es Taller salgan unos y si es Domicilio otros
    campos_dinamicos = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.subtipo_servicio == subtipo,
        models.CampoFormulario.activo == True
    ).order_by(models.CampoFormulario.orden.asc()).all()

    # 3. LÓGICA DE CALENDARIO Y HORAS (Tu lógica actual)
    if duracion_horas is None:
        duracion_horas = 2 if tipo == "domicilio_taller" else 1

    horas_disponibles = []
    mensaje_error = None
    fecha_seleccionada = fecha
    hora_termino = None

    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            # ... (Aquí va toda tu lógica de validación de lunes a viernes, colación, etc.)
            # Asumamos que llamas a obtener_horas_disponibles() como ya lo tenías
            horas_disponibles = obtener_horas_disponibles(tipo, fecha_obj, duracion_horas, db)
            
            # Calcular término si hay hora seleccionada
            if hora:
                inicio = datetime.combine(fecha_obj, datetime.strptime(hora, "%H:%M").time())
                hora_termino = (inicio + timedelta(hours=duracion_horas)).strftime("%H:%M")
        except Exception as e:
            mensaje_error = "Error al procesar la fecha."

    # 4. RENDER FINAL (Un solo return al final de la función)
    return templates.TemplateResponse("agendar.html", {
        "request": request,
        "tipo": tipo,
        "subtipo": subtipo,
        "fecha_seleccionada": fecha_seleccionada,
        "hora_confirmada": hora,
        "duracion_horas": duracion_horas,
        "horas_disponibles": horas_disponibles,
        "hora_termino": hora_termino,
        "mensaje_error": mensaje_error,
        "campos_dinamicos": campos_dinamicos, # <--- ESTO ES LO QUE USA EL HTML
        "utm_source": "whatsapp",
        "utm_campaign": f"{tipo}_{subtipo}"
    })

buffer_minutos = 10

feriados = [
    "2025-12-25","2026-01-01", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-21",
    "2026-06-10", "2026-07-16", "2026-08-15", "2026-09-18", "2026-09-19",
    "2026-10-12", "2026-11-02", "2026-12-25"
]

@router.post("/agendar_web", response_class=HTMLResponse)
async def recibir_formulario(request: Request, db: Session = Depends(get_db)):
    try:
        form_data = await request.form()
        
        tipo_servicio = form_data.get("tipo_servicio")
        subtipo = form_data.get("subtipo")
        fecha = form_data.get("fecha")
        hora = form_data.get("hora")
        duracion_horas = int(form_data.get("duracion_horas", 1))
        
        # 1. MAPEO DE CAMPOS DINÁMICOS
        respuestas = {}
        campos_db = db.query(models.CampoFormulario).all()
        
        print("--- DEBUG: Mapeando datos ---")
        for c in campos_db:
            valor = form_data.get(f"dinamico_{c.id}")
            if valor:
                nombre_key = c.nombre_tecnico.lower().strip()
                respuestas[nombre_key] = valor
                print(f"✅ {nombre_key}: {valor}")

        # 2. ASIGNACIÓN DE VARIABLES CON FALLBACKS
        rut = respuestas.get("rut")
        nombre = respuestas.get("nombre")
        apellido = respuestas.get("apellido")
        correo = respuestas.get("correo") or respuestas.get("email")
        telefono = respuestas.get("telefono") or respuestas.get("celular")
        marca = respuestas.get("marca")
        modelo = respuestas.get("modelo")
        patente = respuestas.get("patente", "").upper()
        kilometraje = respuestas.get("kilometraje")
        
        direccion = respuestas.get("direccion") or form_data.get("direccion")
        tipo_vivienda = respuestas.get("tipo_vivienda") or form_data.get("tipo_vivienda") or "No especificado"

        # 3. VALIDACIÓN DE CAMPOS OBLIGATORIOS
        if not correo:
            raise Exception("El correo es obligatorio para el agendamiento.")
        if not rut:
            raise Exception("El RUT es obligatorio.")

        # 4. LÓGICA DE FECHAS
        fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        fecha_termino = fecha_inicio + timedelta(hours=duracion_horas, minutes=30) 

        # 5. ASIGNACIÓN DE EQUIPO
        RECURSOS = {
            "especializado": ["Equipo Especializado"],
            "domicilio_taller": ["Equipo Israel", "Equipo Mendez"]
        }
        equipos = RECURSOS.get(tipo_servicio, [])
        reservas = db.query(models.Agendamiento).filter(
            models.Agendamiento.fecha_inicio < fecha_termino,
            models.Agendamiento.fecha_termino > fecha_inicio,
            models.Agendamiento.estado != "cancelado"
        ).all()
        
        equipos_ocupados = {r.equipo for r in reservas}
        equipos_libres = [e for e in equipos if e not in equipos_ocupados]

        if not equipos_libres:
            if tipo_servicio == "domicilio_taller" and subtipo == "domicilio":
                equipo_asignado = "Equipo Movil"
            else:
                raise Exception("No hay equipos disponibles en este horario.")
        else:
            equipo_asignado = equipos_libres[0]

        # 6. GUARDAR EN BASE DE DATOS
        nueva = models.Agendamiento(
            rut=rut, 
            nombre=nombre, 
            apellido=apellido, 
            correo=correo, 
            telefono=telefono,
            tipo_vivienda=tipo_vivienda, 
            direccion=direccion,
            marca=marca, 
            modelo=modelo, 
            patente=patente, 
            kilometraje=kilometraje,
            tipo_servicio=tipo_servicio, 
            subtipo=subtipo, 
            equipo=equipo_asignado,
            fecha_inicio=fecha_inicio, 
            fecha_termino=fecha_termino, 
            duracion_horas=duracion_horas,
            estado="pendiente"
        )
        db.add(nueva)
        db.commit()
        db.refresh(nueva)
    # 7. ENVÍO DE AVISO INICIAL
        try:
        # 1. ESTO ES LO ÚNICO QUE LLEGA AL AGENDAR
            enviar_aviso_recibido_cliente(nueva) 
            
            print(f"✅ Aviso de 'Solicitud Recibida' enviado a: {correo}")

            # ❌ NO enviar nada más aquí. 
            # El botón verde llegará solo en 5 min gracias al Scheduler.
        except Exception as e:
            print(f"⚠️ Error al enviar aviso inicial: {e}")

        return templates.TemplateResponse("agendar.html", {
            "request": request,
            "success": True,
            "horas_disponibles": [],
            "tipo": tipo_servicio,
            "subtipo": subtipo
        })

    except Exception as e:
        db.rollback()
        print(f"❌ ERROR EN AGENDAMIENTO: {e}")
        return templates.TemplateResponse("agendar.html", {
            "request": request,
            "mensaje_error": str(e),
            "tipo": form_data.get("tipo_servicio"),
            "subtipo": form_data.get("subtipo"),
            "fecha_seleccionada": None
        })

def carga_equipo_en_dia(db: Session, equipo: str, fecha: date) -> int:
    return db.query(models.Agendamiento).filter(
        models.Agendamiento.equipo == equipo,
        func.date(models.Agendamiento.fecha_inicio) == fecha
    ).count()

def calcular_fin_especializado(inicio: datetime, duracion: int) -> datetime:
    horas_asignadas = 0
    actual = inicio

    while horas_asignadas < duracion:
        # Si justo llegamos a las 12:00, saltamos directo a las 13:00s
        if actual.hour == 12 and actual.minute == 0:
            actual = actual.replace(hour=13, minute=0)
        else:
            actual += timedelta(hours=1)
            horas_asignadas += 1

    return actual

Recursos = {
    "domicilio_taller": ["israel", "mendez"],
    "especializado": ["especializado"]
}  

Horarios_base = ["09:00", "13:00", "15:30"]

CUPOS_TIPO = {
    "especializado": 3,
    "domicilio_taller": 6
}


def obtner_cupos_disponibles(tipo_servicio, fecha, duracion, db):
    recursos = Recursos[tipo]
    cupos = []

    for recurso in recursos:
        for hora in Horarios_base:
            existe = db.query(Agendamiento).filter(
                Agendamiento.fecha == fecha,
                Agendamiento.hora == hora,
                Agendamiento.recurso == recurso,
            ).first()

            if not existe:
                cupos.append({
                    "hora": hora,
                    "recurso":recurso
                })
    return cupos



def obtener_horas_disponibles(tipo_servicio, fecha, duracion_horas, db):
    horas_disponibles = []
    equipos = Recursos.get(tipo_servicio, [])

    if not equipos:
        return []

    # Obtener el día de la semana (0=Lunes, 2=Miércoles)
    dia_semana = fecha.weekday() 

    for h in Horarios_base:
        # --- NUEVA LÓGICA DE MIÉRCOLES ---
        # Si es miércoles (2) y la hora es 15:30, la saltamos de inmediato
        if dia_semana == 2 and h == "15:30":
            continue 
        # ---------------------------------

        inicio = datetime.combine(fecha, datetime.strptime(h, "%H:%M").time())
        
        # Usamos tu función de verificar_disponibilidad para validar reglas de negocio
        # (Feriados, colación, etc.)
        if not verificar_disponibilidad(db, tipo_servicio, inicio, duracion_horas):
            continue

        # Validar traslapes con equipos específicos
        termino = inicio + timedelta(hours=duracion_horas, minutes=buffer_minutos)
        
        reservas = db.query(models.Agendamiento).filter(
            models.Agendamiento.fecha_inicio < termino,
            models.Agendamiento.fecha_termino > inicio,
            models.Agendamiento.estado != "cancelado"
        ).all()

        equipos_ocupados = {r.equipo for r in reservas}

        # Si aún hay equipos libres, la hora es válida
        if len(equipos_ocupados) < len(equipos):
            horas_disponibles.append(h)

    return horas_disponibles


def carga_equipo_en_dia(db, equipo, fecha):
    inicio = datetime.combine(fecha, time(0, 0))
    fin = datetime.combine(fecha, time(23, 59))

    return db.query(models.Agendamiento).filter(
        models.Agendamiento.equipo == equipo,
        models.Agendamiento.fecha_inicio >= inicio,
        models.Agendamiento.fecha_inicio <= fin
    ).count()

def verificar_disponibilidad(db: Session, tipo_servicio: str, inicio: datetime, duracion_horas: int) -> bool:

    tz_chile = pytz.timezone("America/Santiago")
    
    if inicio.tzinfo is None:
        inicio = tz_chile.localize(inicio)

    # Definir 'fin' al principio para que esté disponible para todas las validaciones
    if tipo_servicio == "especializado":
        fin = calcular_fin_especializado(inicio, duracion_horas)
    else:
        fin = inicio + timedelta(hours=duracion_horas)

    # Ahora sí podemos sacar los tiempos
    h_inicio = inicio.time()
    h_fin = fin.time()
    
    # REGLA GENERAL: 08:00 - 18:00
    if h_inicio < time(8, 0) or h_fin > time(18, 0):
        return False

    # REGLA COLACIÓN: No puede cruzar de 12:00 a 13:00
    if h_inicio < time(13, 0) and h_fin > time(12, 0):
        return False

    # 5. VALIDACIÓN POR TIPO DE SERVICIO
    dia_semana = inicio.weekday() # 0:Lunes, 2:Miércoles...
    hora_str = inicio.strftime("%H:%M")

    if tipo_servicio == "domicilio_taller":
        if duracion_horas != 2:
            return False
            
        # --- REGLA ESPECÍFICA MIÉRCOLES ---
        if dia_semana == 2: # Es Miércoles
            if hora_str not in ["09:00", "13:00"]:
                return False
        # --- REGLA OTROS DÍAS ---
        else:
            if hora_str not in ["09:00", "13:00", "15:30"]:
                return False

    elif tipo_servicio == "especializado":
        # Para especializado, validamos que el bloque no sea Miércoles 15:30 
        # (Opcional: Si el miércoles solo hay 09:00 y 13:00 para TODO, usa el bloque de arriba)
        if dia_semana == 2 and hora_str not in ["09:00", "13:00"]:
            return False
    else:
        return False

    # 6. Validar traslapes en la DB
    agendados = db.query(models.Agendamiento).filter(
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio
    ).all()

    return len(agendados) == 0

def enviar_correo_confirmacion(destino, asunto, contenido):
    try:
        # tu lógica SMTP o servicio externo aquí
        print("📨 Correo enviado a:", destino)
        return True
    except Exception as e:
        print("❌ Error enviando correo:", e)
        return False
        
@router.get("/confirmar/{agendamiento_id}")
async def confirmar_cita_endpoint(agendamiento_id: int, db: Session = Depends(get_db)):
    agendamiento = db.query(models.Agendamiento).filter(models.Agendamiento.id == agendamiento_id).first()
    
    if not agendamiento:
        return HTMLResponse("ID no válido")

    # Si ya se confirmó, no hacemos nada más
    if agendamiento.estado != "confirmado":
        agendamiento.estado = "confirmado"
        db.commit()
        # Disparo inmediato de los correos finales
        enviar_confirmacion_agendamiento(agendamiento, "Confirmación Exitosa")
        enviar_aviso_accion_al_dueno(agendamiento, "ACEPTADA ✅")

    # RESPUESTA PARA MÓVIL: Una pantalla que se cierra o avisa éxito inmediato
    return HTMLResponse("""
        <html>
            <head>
                <meta name="viewport" content="width=device-width, initial-scale=1">
                <style>
                    body { font-family: sans-serif; text-align: center; padding-top: 50px; background: #f4f7f6; color: #1e293b; }
                    .loader { border: 4px solid #f3f3f3; border-top: 4px solid #10b981; border-radius: 50%; width: 30px; height: 30px; animation: spin 1s linear infinite; margin: 20px auto; }
                    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
                </style>
            </head>
            <body>
                <h2 style="color:#10b981;">✅ ¡Listo!</h2>
                <p>Tu cita en <b>Tommy Crozier</b> ha sido confirmada.</p>
                <p>Revisa tu correo ahora para ver el calendario.</p>
                <script>
                    // Intentamos cerrar la pestaña tras 2 segundos
                    setTimeout(function(){ 
                        window.close(); 
                        // En algunos móviles window.close() no funciona si no fue abierto por JS,
                        // por lo que el mensaje de arriba es el respaldo perfecto.
                    }, 2500);
                </script>
            </body>
        </html>
    """)