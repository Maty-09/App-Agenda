from fastapi import APIRouter, Depends, HTTPException,Request, Form, Query
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.database import SessionLocal
from app.utils.email_utils import enviar_correo_confirmacion, enviar_correo_cancelacion
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
    tipo: str = Query(None, description="especializado o domicilio_taller"),
    subtipo: str = Query(None, description="taller o domicilio"),
    fecha: str = Query(None),
    hora: str = Query(None),
    duracion_horas: int = Query(None),
    db: Session = Depends(get_db)
):
    """
    Formulario de agendamiento con validaciones:
    - Lunes a viernes
    - Horario laboral
    - Colación
    - No fechas u horas pasadas
    """

    # =========================
    # Normalizar parámetros
    # =========================
    tipo = tipo.lower().strip() if tipo else None
    subtipo = subtipo.lower().strip() if subtipo else None

    # =========================
    # Validar tipo
    # =========================
    if tipo not in ["especializado", "domicilio_taller"]:
        return RedirectResponse(
            url="/cliente/agendar_web?tipo=domicilio_taller",
            status_code=302
        )

    if tipo == "domicilio_taller" and subtipo not in ["taller", "domicilio"]:
        raise HTTPException(
            status_code=400,
            detail="Debes especificar subtipo: taller o domicilio"
        )

    # =========================
    # Duración por defecto
    # =========================
    if duracion_horas is None:
        duracion_horas = 2 if tipo == "domicilio_taller" else 1

    horas_disponibles = []
    mensaje_error = None
    fecha_seleccionada = fecha

    # =========================
    # Procesar fecha
    # =========================
    if fecha:
        try:
            fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
            hoy = date.today()
            ahora = datetime.now().time()

            if fecha_obj < hoy:
                mensaje_error = "No puedes agendar en una fecha anterior a hoy."

            elif fecha_obj.weekday() > 4:
                mensaje_error = "Solo se puede agendar de lunes a viernes."

            else:
                horas_base = obtener_horas_disponibles(
                    tipo,
                    fecha_obj,
                    duracion_horas,
                    db
                )

                for h in horas_base:
                    h_inicio = datetime.strptime(h, "%H:%M").time()
                    h_fin = (
                        datetime.combine(fecha_obj, h_inicio)
                        + timedelta(hours=duracion_horas)
                    ).time()

                    # Hoy → bloquear horas pasadas
                    if fecha_obj == hoy and h_inicio <= ahora:
                        continue

                    # Colación
                    if (time(12, 0) <= h_inicio < time(13, 0)) or \
                       (time(12, 0) < h_fin <= time(13, 0)):
                        continue

                    # Horario laboral
                    if not (time(8, 0) <= h_inicio and h_fin <= time(18, 0)):
                        continue

                    # Miércoles → máximo hasta 17:00
                    if fecha_obj.weekday() == 2:
                        if h_fin > time(17, 0):
                            continue


                    horas_disponibles.append(h)

        except ValueError as e:
            print("Error fecha:", e)
            mensaje_error = "Error procesando la fecha seleccionada."

    # =========================
    # Dirección según subtipo
    # =========================
    direccion_fija = None
    mostrar_campo_direccion = True

    if tipo == "domicilio_taller" and subtipo == "taller":
        direccion_fija = "Av. Los Talleres 123, Santiago"
        mostrar_campo_direccion = False

    # =========================
    # Tipo de vivienda (solo domicilio)
    # =========================
    mostrar_tipo_vivienda = False
    if tipo == "domicilio_taller" and subtipo == "domicilio":
        mostrar_tipo_vivienda = True

    # =========================
    # Calcular hora de término
    # =========================
    hora_termino = None

    if fecha_seleccionada and hora:
        try:
            fecha_obj = datetime.strptime(fecha_seleccionada, "%Y-%m-%d").date()
            hora_obj = datetime.strptime(hora.strip(), "%H:%M").time()

            inicio = datetime.combine(fecha_obj, hora_obj)
            hora_termino = (
                inicio + timedelta(hours=duracion_horas)
            ).strftime("%H:%M")

        except ValueError as e:
            print("Error fecha/hora:", e)


    # =========================
    # UTM
    # =========================
    utm_source = "whatsapp"
    utm_medium = "link_admin"

    if tipo == "especializado":
        utm_campaign = f"especializado_{duracion_horas}h"
    elif tipo == "domicilio_taller":
        utm_campaign = f"domiclio_taller_{subtipo}"
    else:
        utm_campaign = "desconocido"

    # =========================
    # Render
    # =========================
    print("HORAS DISPONIBLES", horas_disponibles)
    return templates.TemplateResponse(
        "agendar.html",
        {
            "request": request,
            "tipo": tipo,
            "subtipo": subtipo,
            "fecha_seleccionada": fecha_seleccionada,
            "hora_confirmada": hora,
            "duracion_horas": duracion_horas,
            "horas_disponibles": horas_disponibles,
            "hora_termino": hora_termino,
            "direccion_fija": direccion_fija,
            "mostrar_campo_direccion": mostrar_campo_direccion,
            "mostrar_tipo_vivienda": mostrar_tipo_vivienda,
            "mensaje_error": mensaje_error,
            "tipo_servicio": tipo,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign,
        }
    )


buffer_minutos = 10

feriados = [
    "2025-12-25","2026-01-01", "2026-04-02", "2026-04-03", "2026-05-01", "2026-05-21",
    "2026-06-10", "2026-07-16", "2026-08-15", "2026-09-18", "2026-09-19",
    "2026-10-12", "2026-11-02", "2026-12-25"
]

@router.post("/agendar_web", response_class=HTMLResponse)
def recibir_formulario(
    request: Request,
    tipo_servicio: str = Form(...),
    subtipo: str = Form(None),
    fecha: str = Form(...),
    hora: str = Form(...),
    duracion_horas: int = Form(...),

    rut: str = Form(...),
    nombre: str = Form(...),
    apellido: str = Form(...),
    correo: str = Form(...),
    telefono: str = Form(...),

    tipo_vivienda: str = Form(...),
    direccion: str = Form(None),

    marca: str = Form(...),
    modelo: str = Form(...),
    patente: str = Form(...),
    kilometraje: int = Form(None),

    origen_link: str = Form("link_directo"),
    canal: str = Form("whatsapp"),

    db: Session = Depends(get_db)
):
    try:
        # ================================
        # FECHA / HORA
        # ================================
        fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        fecha_termino = fecha_inicio + timedelta(
            hours=duracion_horas,
            minutes=buffer_minutos
        )

        # ================================
        # FERIADOS
        # ================================
        if fecha_inicio.strftime("%Y-%m-%d") in feriados:
            raise HTTPException(400, "No se atiende en feriados")

        # ================================
        # RECURSOS DISPONIBLES
        # ================================
        RECURSOS = {
            "especializado": ["Equipo Especializado"],
            "domicilio_taller": ["Equipo Israel", "Equipo Mendez"]
        }

        equipos = RECURSOS.get(tipo_servicio, [])

        if not equipos:
            raise HTTPException(400, "Tipo de servicio inválido")

        # ================================
        # RESERVAS EXISTENTES
        # ================================
        reservas = db.query(models.Agendamiento).filter(
            models.Agendamiento.tipo_servicio == tipo_servicio,
            models.Agendamiento.fecha_inicio < fecha_termino,
            models.Agendamiento.fecha_termino > fecha_inicio
        ).all()

        equipos_ocupados = {r.equipo for r in reservas}
        equipos_libres = [e for e in equipos if e not in equipos_ocupados]

        if not equipos_libres:
            raise HTTPException(400, "No hay equipos disponibles para este horario")

        # ================================
        # ASIGNACIÓN FINAL
        # ================================
        if tipo_servicio == "domicilio_taller":
            if subtipo == "domicilio":
                equipo_asignado = "Equipo Movil"
        else:
            carga_israel = carga_equipo_en_dia(db, "Equipo Israel", fecha_inicio.date())
            carga_mendez = carga_equipo_en_dia(db, "Equipo Mendez", fecha_inicio.date())

            equipo_asignado = (
                "Equipo Israel"
                if carga_israel <= carga_mendez
                else "Equipo Mendez"
            )
        # ================================
        # REGLA MIÉRCOLES
        # ================================
        if fecha_inicio.weekday() == 2:  # 0=lunes ... 2=miércoles
            cierre_miercoles = fecha_inicio.replace(hour=17, minute=0, second=0)

            if fecha_termino > cierre_miercoles:
                return templates.TemplateResponse(
                    "agendar.html",
                    {
                        "request": request,
                        "error": "⚠️ Los días miércoles solo se atiende hasta las 17:00 hrs.",
                        "fecha_seleccionada": fecha,
                        "hora_confirmada": hora,
                        "duracion_horas": duracion_horas,
                        "horas_disponibles": obtener_horas_disponibles(
                            tipo_servicio,
                            fecha_inicio.date(),
                            duracion_horas,
                            db
                        )
                    }
                )


        # ================================
        # GUARDAR
        # ================================
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
            patente=patente.upper(),
            kilometraje=kilometraje,

            tipo_servicio=tipo_servicio,
            subtipo=subtipo,
            equipo=equipo_asignado,

            fecha_inicio=fecha_inicio,
            fecha_termino=fecha_termino,
            duracion_horas=duracion_horas
        )

        db.add(nueva)
        db.commit()
        #db.refresh(nueva)

        utm = models.UTMRegistro(
            agendamiento_id = nueva.id,
            utm_source= origen_link,
            utm_medium = canal,
            utm_campaign = tipo_servicio,
            fecha_registro = datetime.now()
        )

        db.add(utm)
        db.commit()

        correo_ok = enviar_correo_confirmacion(
        nueva.correo,
        "Confirmación de Mantención",
        f"""
        Hola {nueva.nombre},

        Tu mantención fue agendada con éxito ✅

        📅 Fecha: {nueva.fecha_inicio.strftime('%d-%m-%Y')}
        🕒 Hora: {nueva.fecha_inicio.strftime('%H:%M')}
        🚗 Vehículo: {nueva.marca} {nueva.modelo}
        🔧 Equipo: {nueva.equipo}

        Gracias por confiar en nosotros.
        """
        )

        if not correo_ok:
            print("⚠️ Mantención creada pero correo NO enviado")


        print("✔ Mantención creada ID:", nueva.id)

        return templates.TemplateResponse(
            "agendar.html",
            {
                "request": request,
                "success": "✅ Mantención agendada correctamente",
                "horas_disponibles": []
            }
        )

    except Exception as e:
        db.rollback()
        print("❌ ERROR AGENDANDO:", e)

        return templates.TemplateResponse(
            "agendar.html",
            {
                "request": request,
                "error": str(e),
                "fecha_seleccionada": fecha,
                "hora_confirmada": hora
            }
        )

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

    for h in Horarios_base:
        inicio = datetime.combine(fecha, datetime.strptime(h, "%H:%M").time())
        termino = inicio + timedelta(hours=duracion_horas, minutes=buffer_minutos)

        # Reservas que chocan
        reservas = db.query(models.Agendamiento).filter(
            models.Agendamiento.tipo_servicio == tipo_servicio,
            models.Agendamiento.fecha_inicio < termino,
            models.Agendamiento.fecha_termino > inicio
        ).all()

        equipos_ocupados = {r.equipo for r in reservas}

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

    #zona horaria local 
    tz_chile = pytz.timezone("America/Santiago")
    ahora = datetime.now(tz_chile)
     # ❌ Bloquear sábados (5) y domingos (6)
    if inicio.weekday() >= 5:
        return False
    if inicio.tzinfo is None :
        inicio = tz_chile.localize(inicio)

    if inicio < ahora:
        return False
    
     # 🕗 Horario laboral: 08:00 - 18:00 (colación 12:00 - 13:00)
    hora_inicio_jornada = time(8, 0)
    hora_termino_jornada = time(18, 0)
    hora_colacion_inicio = time(12, 0)
    hora_colacion_termino = time(13, 0)

     # ❌ Fuera de horario laboral
    if not (hora_inicio_jornada <= inicio.time() < hora_termino_jornada and fin.time() <= hora_termino_jornada):
        return False
    
      # ❌ Cruza el horario de colación
    if (inicio.time() < hora_colacion_termino and fin.time() > hora_colacion_inicio):
        return False

    if tipo_servicio == "especializado":
        # Validar horario laboral
        fin = calcular_fin_especializado(inicio, duracion_horas)
        if not (8 <= inicio.hour < 18 and fin.hour <= 18):
            return False
        
    elif tipo_servicio == "domicilio_taller":
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

def enviar_correo_confirmacion(destino, asunto, contenido):
    try:
        # tu lógica SMTP o servicio externo aquí
        print("📨 Correo enviado a:", destino)
        return True
    except Exception as e:
        print("❌ Error enviando correo:", e)
        return False
