from fastapi import APIRouter, Depends, HTTPException,Request, Query, Form
from sqlalchemy.orm import Session
from datetime import datetime, date, time, timedelta
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from app.core.database import SessionLocal , get_db
from app.infrastructure.email_utils import (
    enviar_confirmacion_agendamiento,
    enviar_aviso_accion_al_dueno,
    enviar_solicitud_confirmacion,
    enviar_aviso_recibido_cliente
)
from app.core.generar_utm import generar_utm 
from app.core import models
from app.infrastructure.notifications import enviar_notificacion
from sqlalchemy import func
import json
import pytz
import traceback


# pruebas
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter()

import os
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@router.get("/agendar_web", response_class=HTMLResponse)
@router.get("/{tenant_id}/agendar_web", response_class=HTMLResponse)
def agendar_web(
    request: Request,
    tipo: str = Query(None),
    subtipo: str = Query(None),
    fecha: str = Query(None),
    hora: str = Query(None),
    duracion_horas: int = Query(None),
    db: Session = Depends(get_db),
    tenant_id: str = "default"
):
    if not db.query(models.Tenant.id).filter(models.Tenant.id == tenant_id).first():
        raise HTTPException(status_code=404, detail="Tenant no encontrado")
    # 1. NORMALIZACIÓN Y VALIDACIÓN INICIAL
    tipo = tipo.lower().strip() if tipo else "domicilio_taller"
    subtipo = subtipo.lower().strip() if subtipo else "local"
    subtipo_db = "taller" if subtipo == "local" else subtipo

    if tipo not in ["domicilio_taller"]:
        return RedirectResponse(url="/cliente/agendar_web?tipo=domicilio_taller", status_code=302)

    # 2. OBTENER CAMPOS DINÁMICOS (Lo que configuraste en el Admin)
    # Filtramos por el subtipo para que si es Local salgan unos y si es Domicilio otros
    campos_dinamicos = db.query(models.CampoFormulario).filter(
        models.CampoFormulario.tenant_id == tenant_id,
        models.CampoFormulario.subtipo_servicio == subtipo_db,
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
            horas_disponibles = obtener_horas_disponibles(tipo, fecha_obj, duracion_horas, db, tenant_id)
            
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
        ,"booking_path": f"/cliente/{tenant_id}/agendar_web" if tenant_id != "default" else "/cliente/agendar_web"
    })

buffer_minutos = 10

import holidays
feriados_cl = holidays.country_holidays('CL')


def dias_habiles_tenant(db: Session, tenant_id: str) -> set[int]:
    """Días permitidos por tenant (0=lunes … 6=domingo)."""
    tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
    try:
        config = json.loads(tenant.config_json or "{}")
        dias = config.get("reglas_negocio", {}).get("dias_habiles", [0, 1, 2, 3, 4])
        return {int(dia) for dia in dias}
    except (AttributeError, ValueError, TypeError, json.JSONDecodeError):
        return {0, 1, 2, 3, 4}

@router.post("/agendar_web", response_class=HTMLResponse)
@router.post("/{tenant_id}/agendar_web", response_class=HTMLResponse)
async def recibir_formulario(request: Request, db: Session = Depends(get_db), tenant_id: str = "default"):
    print("\n--- INICIO DE PROCESAMIENTO POST ---")
    try:
        if not db.query(models.Tenant.id).filter(models.Tenant.id == tenant_id).first():
            raise HTTPException(status_code=404, detail="Tenant no encontrado")
        form_data = await request.form()
        print(f"Datos recibidos: {dict(form_data)}")
        
        tipo_servicio = form_data.get("tipo_servicio")
        subtipo = form_data.get("subtipo")
        subtipo = subtipo.lower().strip() if subtipo else "local"
        subtipo_db = "taller" if subtipo == "local" else subtipo
        fecha = form_data.get("fecha")
        hora = form_data.get("hora")
        
        # --- 1. DETECTAR MODO EMERGENCIA (DUEÑO) ---
        # Lo detectamos si viene en la URL o en un campo oculto del formulario
        es_dueno = (request.query_params.get("modo") == "emergencia" or 
                    form_data.get("modo_emergencia") == "true" or
                    form_data.get("modo") == "emergencia")
        print(f"Es dueno/admin: {es_dueno}")

        nota_interna = form_data.get("nota_interna", "")

        # Validación de 48h hábiles (Se salta si es el dueño)
        fecha_minima = obtener_fecha_minima_habil(db, tenant_id)
        fecha_cliente = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        fecha_cliente = pytz.timezone('America/Santiago').localize(fecha_cliente)

        # --- 2. VALIDACIONES DE FECHA (SE SALTAN SI ES DUEÑO) ---
        if not es_dueno:
            # Regla A: 48h hábiles
            fecha_minima = obtener_fecha_minima_habil(db, tenant_id)
            if fecha_cliente < fecha_minima:
                # En entornos de pruebas podemos permitir el agendamiento aun cuando
                # no cumpla 48h hábiles. Registramos una nota interna y continuamos.
                print(f"Validacion 48H fallida: fecha_cliente={fecha_cliente}, fecha_minima={fecha_minima}; se permite para pruebas.")
                # Añadir marca en la nota interna para identificar excepciones
                nota_interna = (nota_interna or "") + " | EXCEPCION_48H"
            
            # Regla B: Verificar si el día está bloqueado manualmente
            dia_bloqueado = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.tenant_id == tenant_id, models.DiaBloqueado.fecha == fecha).first()
            if dia_bloqueado:
                return templates.TemplateResponse("agendar.html", {
                    "request": request,
                    "mensaje_error": "Este día el local se encuentra cerrado. Por favor selecciona otra fecha.",
                    "tipo": tipo_servicio,
                    "subtipo": subtipo
                })
        duracion_horas = int(form_data.get("duracion", 2))
        fecha_termino = fecha_cliente + timedelta(hours=duracion_horas)

        equipos_oficiales = ["Cristhian", "Samuel", "Movil"]
        equipo_asignado = None

        # 3. MAPEO DE CAMPOS DINÁMICOS
        respuestas = {}
        campos_db = db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == tenant_id).all()
        print("\n--- DEBUG: Mapeando datos desde el Formulario ---")
        
        # Crear mapa de mapeos de nombres técnicos a claves normalizadas
        mapeo_nombres = {
            "rut": ["rut", "run"],
            "correo": ["correo", "email", "mail", "e-mail"],
            "nombre": ["nombre"],
            "apellido": ["apellido"],
            "telefono": ["telefono", "phone", "celular"],
            "marca": ["marca"],
            "modelo": ["modelo"],
            "patente": ["patente", "patent"],
            "kilometraje": ["kilometraje", "kilometros"],
            "direccion": ["direccion", "dirección", "address"],
            "tipo_vivienda": ["tipo_vivienda", "tipo vivienda"]
        }
        
        for c in campos_db:
            valor = form_data.get(f"dinamico_{c.id}")
            if valor:
                nombre_tecnico_normalizado = c.nombre_tecnico.lower().strip()
                
                # Buscar la clave normalizada correcta
                clave_final = None
                for clave_standard, aliases in mapeo_nombres.items():
                    if nombre_tecnico_normalizado in aliases:
                        clave_final = clave_standard
                        break
                
                # Si no encontró mapeo, usar el nombre técnico tal cual
                if not clave_final:
                    clave_final = nombre_tecnico_normalizado
                
                respuestas[clave_final] = valor
                print(f"Campo {c.nombre_tecnico} (ID {c.id}) -> {clave_final}: {valor}")
        
        print(f"Respuestas finales mapeadas: {respuestas}")

        # 2. ASIGNACIÓN DE VARIABLES (Mejorado con fallbacks)
        rut = respuestas.get("rut")
        nombre = respuestas.get("nombre")
        apellido = respuestas.get("apellido")
        correo = respuestas.get("correo")
        telefono = respuestas.get("telefono")
        marca = respuestas.get("marca")
        modelo = respuestas.get("modelo")
        patente = (respuestas.get("patente") or "").upper()
        kilometraje = respuestas.get("kilometraje")
        direccion = respuestas.get("direccion") or form_data.get("direccion")
        tipo_vivienda = respuestas.get("tipo_vivienda") or form_data.get("tipo_vivienda") or "No especificado"

        # 3. VALIDACIÓN DE CAMPOS OBLIGATORIOS
        print(f"\nVALIDACIÓN:")
        print(f"  RUT: {rut}")
        print(f"  Correo: {correo}")
        print(f"  Nombre: {nombre}")
        print(f"  Apellido: {apellido}")
        
        if not correo or not rut:
            raise Exception(f"El correo y el RUT son obligatorios. Recibido: rut={rut}, correo={correo}")

        # 4. LÓGICA DE DURACIÓN
        try:
            duracion_form = form_data.get("duracion_horas")
            duracion_horas = int(duracion_form) if duracion_form else 2
        except:
            duracion_horas = 2

        fecha_inicio = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
        fecha_termino = fecha_inicio + timedelta(hours=duracion_horas)
        # --- 5. LÓGICA DE ASIGNACIÓN AUTOMÁTICA DE EQUIPO ---
        # Definimos los equipos por tipo de servicio
        equipos_posibles = Recursos.get(tipo_servicio, [])
        
        # Si no hay equipos definidos para este tipo, usamos los de domicilio_taller como fallback
        if not equipos_posibles:
            print(f"Alerta: tipo_servicio '{tipo_servicio}' no definido en Recursos. Usando fallback.")
            equipos_posibles = Recursos.get("domicilio_taller", ["Equipo Local"])
        
        equipo_asignado = None

        for eq in equipos_posibles:
            # ¿Este equipo específico está ocupado a esta hora?
            ocupado = db.query(models.Agendamiento).filter(
                models.Agendamiento.tenant_id == tenant_id,
                models.Agendamiento.equipo == eq,
                models.Agendamiento.fecha_inicio < fecha_termino,
                models.Agendamiento.fecha_termino > fecha_inicio,
                models.Agendamiento.estado != "cancelado"
            ).first()
            
            if not ocupado:
                equipo_asignado = eq
                break # Asignamos al primero que esté libre y paramos
        
        # Si no hay equipo libre pero es el DUEÑO, forzamos el primero de la lista (Sobrecupo)
        if not equipo_asignado and es_dueno:
            equipo_asignado = equipos_posibles[0] if equipos_posibles else "Equipo Local"
            print(f"Modo emergencia: sobrecupo detectado. Asignando a {equipo_asignado}")

        if not equipo_asignado:
            # Fallback final: asignar equipo por defecto incluso si nada está libre
            equipo_asignado = equipos_posibles[0] if equipos_posibles else "Equipo Local"
            print(f"Fallback: todos los equipos ocupados. Asignando {equipo_asignado}")
            
        # 6. LÓGICA CRM: CREAR O BUSCAR CLIENTE
        import json
        cliente = db.query(models.Cliente).filter(
            models.Cliente.rut == rut,
            models.Cliente.tenant_id == tenant_id
        ).first()

        if not cliente:
            cliente = models.Cliente(
                tenant_id=tenant_id,
                rut=rut,
                nombre=nombre,
                apellido=apellido,
                telefono=telefono,
                correo=correo,
                etiquetas=json.dumps(["Web"])
            )
            db.add(cliente)
            db.flush()
        else:
            # Actualizar datos de contacto si cambiaron
            if telefono != cliente.telefono or correo != cliente.correo:
                cliente.telefono = telefono
                cliente.correo = correo
                db.flush()

        # 7. GUARDAR EN BASE DE DATOS
        nueva = models.Agendamiento(
            tenant_id=tenant_id,
            cliente_id=cliente.id,
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
            subtipo=subtipo_db, 
            equipo=equipo_asignado,
            fecha_inicio=fecha_inicio, 
            fecha_termino=fecha_termino, 
            duracion_horas=duracion_horas,
            nota_interna = nota_interna,
            estado="pendiente"
        )
        db.add(nueva)
        db.flush()
        
        # 8. REGISTRAR TIMELINE EVENT
        evento = models.TimelineEvent(
            tenant_id=tenant_id,
            cliente_id=cliente.id,
            tipo_evento="RESERVA",
            metadata_json=json.dumps({
                "agendamiento_id": nueva.id,
                "fecha": str(nueva.fecha_inicio),
                "origen": "Web"
            })
        )
        db.add(evento)
        
        db.commit()
        db.refresh(nueva)
        
        print("=" * 80)
        print("GUARDADO EXITOSO EN DB")
        print(f"   ID: {nueva.id}")
        print(f"   Nombre: {nueva.nombre}")
        print(f"   Tipo Servicio: {nueva.tipo_servicio}")
        print(f"   Subtipo (DB): {nueva.subtipo}")
        print(f"   Equipo: {nueva.equipo}")
        print(f"   Fecha: {nueva.fecha_inicio}")
        print(f"   Estado: {nueva.estado}")
        print("=" * 80)
    # 7. ENVÍO DE AVISO INICIAL
        try:
        # 1. ESTO ES LO ÚNICO QUE LLEGA AL AGENDAR
            enviar_notificacion(nueva.id, "creada")
            
            print(f"Aviso de solicitud recibida enviado a: {correo}")

            # ❌ NO enviar nada más aquí. 
            # El botón verde llegará solo en 5 min gracias al Scheduler.
        except Exception as e:
            print(f"Error al enviar aviso inicial: {e}")

        return templates.TemplateResponse("agendar.html", {
            "request": request,
            "success": True,
            "horas_disponibles": [],
            "tipo": tipo_servicio,
            "subtipo": subtipo
        })

    except Exception as e:
        db.rollback()
        print(f"ERROR EN AGENDAMIENTO: {e}")
        error_trace = traceback.format_exc()
        print(f"ERROR CRITICO EN RENDER:\n{error_trace}")
        print(f"ERROR DETALLE: {traceback.format_exc()}")
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
    "domicilio_taller": ["Equipo Cristhian", "Equipo Samuel", "Equipo Movil"], # 3 equipos para este tipo
    "especializado": ["Equipo Cristhian", "Equipo Samuel", "Equipo Movil"],
}

Horarios_base = ["09:00", "13:00", "15:30"]

CUPOS_TIPO = {
    "especializado": 3,
    "domicilio_taller": 6
}


def obtner_cupos_disponibles(tipo_servicio, fecha, duracion, db):
    recursos = Recursos.get(tipo_servicio, [])
    cupos = []

    for recurso in recursos:
        for hora in Horarios_base:
            existe = db.query(models.Agendamiento).filter(
                models.Agendamiento.equipo == recurso,
            ).first()

            if not existe:
                cupos.append({
                    "hora": hora,
                    "recurso": recurso
                })
    return cupos



def obtener_horas_disponibles(tipo_servicio, fecha, duracion_horas, db, tenant_id="default"):
    # 1. Bloqueo manual (botón de administración)
    bloqueado = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.tenant_id == tenant_id, models.DiaBloqueado.fecha == fecha).first()
    if bloqueado:
        return []

    horas_disponibles = []
    # IMPORTANTE: Asegúrate que Recursos["domicilio_taller"] tenga 3 nombres de equipos
    equipos = Recursos.get(tipo_servicio, [])
    if not equipos:
        return []

    dia_semana = fecha.weekday() # 0:Lunes, 2:Miércoles

    for h in Horarios_base:
        # --- REGLA ESTRICTA DE MIÉRCOLES ---
        # Si es miércoles (2), el bloque de las 15:30 no existe para nadie.
        if dia_semana == 2 and h == "15:30":
            continue 

        inicio = datetime.combine(fecha, datetime.strptime(h, "%H:%M").time())
        
        # Validaciones de horario general (08:00-18:00) y feriados
        if not verificar_disponibilidad(db, tipo_servicio, inicio, duracion_horas, tenant_id):
            continue

        # --- CONTADOR DE CUPOS POR EQUIPO ---
        termino = inicio + timedelta(hours=duracion_horas)
        
        # Contamos cuántos de tus 3 equipos ya están ocupados en este bloque exacto
        equipos_ocupados = db.query(models.Agendamiento).filter(
            models.Agendamiento.tenant_id == tenant_id,
            models.Agendamiento.fecha_inicio < termino,
            models.Agendamiento.fecha_termino > inicio,
            models.Agendamiento.estado != "cancelado"
        ).count()

        # Si hay 3 equipos y solo hay 0, 1 o 2 ocupados, la hora SIGUE DISPONIBLE
        if equipos_ocupados < len(equipos):
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

def verificar_disponibilidad(db: Session, tipo_servicio: str, inicio: datetime, duracion_horas: int, tenant_id: str = "default") -> bool:

    # 1. NUEVO: Chequear si el día está bloqueado por administración
    dia_bloqueado = db.query(models.DiaBloqueado).filter(models.DiaBloqueado.tenant_id == tenant_id, models.DiaBloqueado.fecha == inicio.date()).first()
    if dia_bloqueado:
        return False  # Si el día está bloqueado, no hay disponibilidad para nadie

    if inicio.weekday() not in dias_habiles_tenant(db, tenant_id):
        return False

    # REGLA: Excluir feriados en Chile
    import holidays
    feriados_cl = holidays.country_holidays('CL')
    if inicio.date() in feriados_cl:
        return False

    tz_chile = pytz.timezone("America/Santiago")
    
    if inicio.tzinfo is None:
        inicio = tz_chile.localize(inicio)

   # 1. Calcular fin
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
    # Contamos cuántos equipos están ocupados en este bloque
    agendados_en_bloque = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio,
        models.Agendamiento.estado != "cancelado"
    ).count()

    limite_equipos = len(Recursos.get(tipo_servicio, []))
    
    return agendados_en_bloque < limite_equipos


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
                <p>Tu cita ha sido confirmada.</p>
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

def obtener_fecha_minima_habil(db: Session, tenant_id: str):
    tz_chile = pytz.timezone('America/Santiago')
    fecha_chequeo = datetime.now(tz_chile)
    horas_contadas = 0
    
    while horas_contadas < 48:
        fecha_chequeo += timedelta(hours=1)
        # 0=Lunes, 4=Viernes, 5=Sábado, 6=Domingo
        if fecha_chequeo.weekday() in dias_habiles_tenant(db, tenant_id):
            horas_contadas += 1
    return fecha_chequeo



@router.get("/api/horas-disponibles")
def api_horas(
    fecha: str, 
    tipo: str = "domicilio_taller", 
    duracion: int = 2, 
    db: Session = Depends(get_db)
):
    try:
        fecha_obj = datetime.strptime(fecha, "%Y-%m-%d").date()
        # Reutilizamos tu función actual que ya tiene todas las reglas
        horas = obtener_horas_disponibles(tipo, fecha_obj, duracion, db)
        return {"horas": horas}
    except Exception:
        return {"horas": []}

