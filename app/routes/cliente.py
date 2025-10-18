from fastapi import APIRouter, Depends,Request, Form, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app import models
from app.utils.email_utils import enviar_correo_confirmacion
from app import models
from sqlalchemy import func

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
    tipo: str = Query(...),
    fecha: str = Query(None),
    hora: str = Query(None),
    duracion_horas: int = None,
    db: Session = Depends(get_db)
):
    
    if tipo not in ["especializado", "domicilio_taller"]:
        return RedirectResponse(url="/", status_code=302)

     # Asignar duración si no vienes
    if duracion_horas is None:
        duracion_horas = 2 if tipo == "domicilio_taller" else 1
    

    
    fecha_seleccionada = fecha
    hora_confirmada = hora
    horas_disponibles = []
    
    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            horas_disponibles = obtener_horas_disponibles(tipo, fecha_obj, duracion_horas, db)
        except ValueError:
            pass
    
    # Si no viene duración y es "domicilio_taller", asumimos 2 horas
    if duracion_horas is None and tipo == "domicilio_taller":
        duracion_horas = 2
    

    return templates.TemplateResponse("agendar.html", {
        "request": request,
        "tipo_servicio": tipo,
        "fecha_seleccionada": fecha_seleccionada,
        "horas_disponibles": horas_disponibles,
        "current_date": date.today().isoformat(),
        "hora_confirmada": hora_confirmada,
        "duracion_horas": duracion_horas,
        "error": None,
        "success": None,
        
    })

@router.post("/agendar_web", response_class=HTMLResponse)
def recibir_formulario(
    request: Request,
    tipo_servicio: str = Form(...),    
    fecha: str = Form(...),
    hora: str = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    correo: str = Form(...),
    telefono: str = Form(...),
    patente: str = Form(...),
    duracion_horas: int = Form(None),  # solo para especializado
    db: Session = Depends(get_db)
):
    try:
        fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        duracion = duracion_horas if tipo_servicio == "especializado" else 2
        fecha_termino = fecha_inicio + timedelta(hours=duracion)
        ahora = datetime.now()
        # Inicializamos conflictos vacíos para evitar error
        conflictos = []

        #Verificacion de horarios
        if fecha_inicio < ahora:
            return templates.TemplateResponse("agendar.html", {
                "request": request,
                "tipo_servicio": tipo_servicio,
                "fecha_seleccionada":fecha,
                "hora_confirmada":None,
                "duracion_horas": duracion_horas,
                "horas_disponibles": obtener_horas_disponibles(tipo_servicio, fecha_inicio.date(), duracion_horas, db),
                "error": "No puedes agendar en una fecha u hora pasada.",
                "success": None
            })

        # Solo validar traslapes si el servicio es especializado
        if tipo_servicio == "especializado":
            conflictos = db.query(models.Agendamiento).filter(
                models.Agendamiento.tipo_servicio == "especializado",
                models.Agendamiento.fecha_inicio < fecha_termino,
                models.Agendamiento.fecha_termino > fecha_inicio
            ).all()

        if conflictos:
            return templates.TemplateResponse("agendar.html", {
                "request": request,
                "tipo_servicio": tipo_servicio,
                "fecha_seleccionada": fecha,
                "duracion_horas": duracion,
                "hora_confirmada": None,
                "horas_disponibles": obtener_horas_disponibles(tipo_servicio, fecha_inicio.date(), duracion, db),
                "error": "Ya existe una mantención especializada en ese bloque horario.",
                "success": None
            })

        nueva = models.Agendamiento(
            nombre=nombre,
            apellido=apellido,
            correo=correo,
            telefono=telefono,
            patente=patente.upper(),
            tipo_servicio=tipo_servicio,
            hora=fecha_inicio.time(),
            duracion_horas=duracion,
            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino
        )
        db.add(nueva)
        db.commit()

        # Enviar correo y whatsapp
        asunto = "Confirmación de Mantención"
        contenido = f"""Hola {nueva.nombre},
Tu mantención fue agendada con éxito:
🧾 Tipo de servicio: {nueva.tipo_servicio}
🕒 Inicio: {nueva.fecha_inicio.strftime('%d-%m-%Y %H:%M')}
⏱️ Término: {nueva.fecha_termino.strftime('%H:%M')}
🚗 Patente: {nueva.patente}
¡Gracias por confiar en nosotros!"""
        enviar_correo_confirmacion(nueva.correo, asunto, contenido)

    except Exception as e:
        return templates.TemplateResponse("agendar.html", {
            "request": request,
            "tipo_servicio": tipo_servicio,
            "fecha_seleccionada": fecha,
            "hora_confirmada": hora,
            "duracion_horas": duracion_horas,
            "horas_disponibles": [],
            "success": "Cita agendada exitosamente",
            "error": "Error al agendar: " + str(e)
        })

   
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


def obtener_horas_disponibles(tipo: str, fecha: date, duracion: int, db: Session):
    disponibles = []
    agendadas = db.query(models.Agendamiento).filter(func.date(models.Agendamiento.fecha_inicio) == fecha).all()

    if tipo == "especializado":
        bloques = [time(8, 0), time(9, 0), time(10, 0), time(11, 0), time(13, 0), time(14, 0), time(15, 0)]
    else:
        bloques = [time(9, 0), time(13, 0), time(15, 30)]
        duracion = 2  # fijo para domicilio/taller

    for bloque in bloques:
        inicio = datetime.combine(fecha, bloque)
        
        if tipo == "especializado":
            fin = calcular_fin_especializado(inicio, duracion)
        else:
            fin = inicio + timedelta(hours=duracion)


        traslape = False
        for a in agendadas:
            ag_inicio = a.fecha_inicio
            ag_fin = a.fecha_termino
            if max(inicio, ag_inicio) < min(fin, ag_fin):
                traslape = True
                break

        if not traslape:
            disponibles.append(bloque.strftime("%H:%M"))

    return disponibles


def verificar_disponibilidad(db: Session, tipo_servicio: str, inicio: datetime, duracion_horas: int) -> bool:
    if tipo_servicio == "especializado":
        fin = calcular_fin_especializado(inicio, duracion_horas)

    if tipo_servicio == "especializado":
        # Validar horario laboral
        if not (8 <= inicio.hour < 16 and fin.hour <= 16):
            return False
    elif tipo_servicio in ["taller", "domicilio"]:
        fin = inicio + timedelta(hours=duracion_horas)
        
        # Validar que sea una hora permitida
        hora_inicio_permitida = inicio.strftime("%H:%M")
        if hora_inicio_permitida not in ["09:00", "13:00", "15:30"]:
            return False

        if duracion_horas != 2:
            return False

    else:
        return False  # tipo no reconocido

    # Validar traslapes para cualquier tipo
    agendados = db.query(models.Agendamiento).filter(
        models.Agendamiento.tipo_servicio == tipo_servicio,
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio
    ).all()

    return len(agendados) == 0
