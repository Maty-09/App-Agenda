from sqlalchemy.orm import Session
import os
from sqlalchemy import func
from datetime import datetime, timedelta
from app.core import models
import pytz
import requests
import json

# Memoria conversacional en RAM (Dicc global)
historial_global = {}

def get_now_chile():
    tz = pytz.timezone('America/Santiago')
    return datetime.now(tz)

def detectar_clientes_inactivos(db: Session, tenant_id: str, umbral_meses: int = 3):
    """
    Identifica clientes que no han tenido agendamientos en los últimos X meses.
    """
    fecha_limite = get_now_chile() - timedelta(days=umbral_meses * 30)
    
    # Subquery: la última cita de cada cliente
    subquery = db.query(
        models.Agendamiento.cliente_id,
        func.max(models.Agendamiento.fecha_inicio).label("ultima_cita")
    ).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.estado != "CANCELADA"
    ).group_by(models.Agendamiento.cliente_id).subquery()
    
    # Clientes cuya última cita es anterior al umbral
    resultados = db.query(models.Cliente, subquery.c.ultima_cita).join(
        subquery, models.Cliente.id == subquery.c.cliente_id
    ).filter(
        subquery.c.ultima_cita < fecha_limite
    ).all()
    
    riesgos = []
    for cliente, ultima_cita in resultados:
        dias_inactivo = (get_now_chile().replace(tzinfo=None) - ultima_cita.replace(tzinfo=None)).days if ultima_cita else 0
        riesgos.append({
            "cliente_id": cliente.id,
            "nombre": f"{cliente.nombre} {cliente.apellido}",
            "telefono": cliente.telefono,
            "dias_inactivo": dias_inactivo,
            "ultima_cita": ultima_cita.strftime("%Y-%m-%d") if ultima_cita else "Desconocida"
        })
        
    # Ordenar por los que llevan más tiempo inactivos
    riesgos.sort(key=lambda x: x["dias_inactivo"], reverse=True)
    return riesgos

def obtener_top_marcas_agendadas(db: Session, tenant_id: str, limit: int = 5):
    """
    Obtiene las marcas de vehículos con más agendamientos históricos reales.
    """
    # Consulta SQLAlchemy para agrupar por marca y contar
    resultados = db.query(
        models.Agendamiento.marca,
        func.count(models.Agendamiento.id).label('total')
    ).filter(
        models.Agendamiento.tenant_id == tenant_id,
        models.Agendamiento.marca != "Por definir",
        models.Agendamiento.marca != None,
        models.Agendamiento.marca != ""
    ).group_by(models.Agendamiento.marca).order_by(
        func.count(models.Agendamiento.id).desc()
    ).limit(limit).all()
    
    return [{"marca": r[0], "citas": r[1]} for r in resultados]

def agendar_cita_ia(db: Session, tenant_id: str, telefono: str, fecha_inicio: datetime, marca: str = "Por definir"):
    """
    Permite al Bot crear una cita basada en la intención de WhatsApp.
    """
    # Buscar si el cliente existe por teléfono
    cliente = db.query(models.Cliente).filter(
        models.Cliente.tenant_id == tenant_id,
        models.Cliente.telefono == telefono,
    ).first()
    
    if not cliente:
        # Crear cliente temporal
        cliente = models.Cliente(
            tenant_id=tenant_id,
            rut=f"N/A-{telefono[-4:]}",
            nombre="Cliente WhatsApp",
            apellido="",
            telefono=telefono,
            correo="sin_correo@whatsapp.com"
        )
        db.add(cliente)
        db.commit()
        db.refresh(cliente)

    # Crear el agendamiento
    cita = models.Agendamiento(
        tenant_id=tenant_id,
        cliente_id=cliente.id,
        rut=cliente.rut,
        tipo_servicio="especializado",  # Debe coincidir con el Enum TipoServicio
        nombre=cliente.nombre,
        apellido=cliente.apellido,
        telefono=cliente.telefono,
        correo=cliente.correo,
        marca=marca,
        modelo="Por definir",
        patente="WSP-002",
        tipo_vivienda="No especificada", # Campo obligatorio
        equipo="Sin equipo asignado",    # Campo obligatorio
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_inicio + timedelta(hours=1)
    )
    db.add(cita)
    db.commit()
    db.refresh(cita)
    return cita

def chat_ia(mensaje: str, db: Session = None, telefono: str = None, tenant_id: str = None) -> str:
    """
    Integración con la API de InceptionLabs. Contextualizada con base de datos si aplica.
    """
    api_key = os.getenv("INCEPTION_API_KEY")
    if not api_key:
        return "La inteligencia artificial no est\u00e1 configurada."
    url = "https://api.inceptionlabs.ai/v1/chat/completions"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Evaluar contexto de datos
    contexto_datos = ""
    es_admin = False
    
    if db:
        # Detectar si el usuario pregunta por marcas
        if "marcas" in mensaje.lower() or "top" in mensaje.lower():
            top_marcas = obtener_top_marcas_agendadas(db, tenant_id)
            contexto_datos = "\n\nDatos Reales de la Base de Datos:\n"
            contexto_datos += "Top Marcas Agendadas:\n"
            for i, m in enumerate(top_marcas):
                contexto_datos += f"{i+1}. {m['marca']} - {m['citas']} citas\n"
        
        # Verificar si el teléfono pertenece a un admin
        if telefono:
            usuario = db.query(models.Usuario).filter(
                models.Usuario.email.like(f"%{telefono}%") # Simple check, idealmente buscaríamos en DB por telefono real
            ).first()
            if usuario and usuario.rol == "admin":
                es_admin = True
                
            # Agregar información de citas del cliente al contexto
            cliente = db.query(models.Cliente).filter(models.Cliente.telefono == telefono).first()
            citas_futuras = []
            if cliente:
                citas_futuras = db.query(models.Agendamiento).filter(
                    models.Agendamiento.cliente_id == cliente.id,
                    models.Agendamiento.fecha_inicio >= get_now_chile().replace(tzinfo=None),
                    models.Agendamiento.estado != "cancelado"
                ).order_by(models.Agendamiento.fecha_inicio.asc()).all()
            else:
                citas_futuras = db.query(models.Agendamiento).filter(
                    models.Agendamiento.telefono == telefono,
                    models.Agendamiento.fecha_inicio >= get_now_chile().replace(tzinfo=None),
                    models.Agendamiento.estado != "cancelado"
                ).order_by(models.Agendamiento.fecha_inicio.asc()).all()

            contexto_datos += "\n\n--- MEMORIA SOBRE EL CLIENTE ACTUAL ---\n"
            if citas_futuras:
                contexto_datos += "El cliente con el que hablas tiene las siguientes citas programadas a futuro:\n"
                for cita in citas_futuras:
                    contexto_datos += f"- Fecha y hora: {cita.fecha_inicio.strftime('%Y-%m-%d %H:%M')}, Servicio: {cita.tipo_servicio}, Marca: {cita.marca}, Estado: {cita.estado}\n"
                contexto_datos += "Usa esta información si el cliente pregunta por sus citas agendadas o confirmaciones.\n"
            else:
                contexto_datos += "El cliente NO tiene ninguna cita agendada a futuro. Si pregunta por sus horas, confírmale que no tiene nada programado y ofrécele agendar.\n"
    
    # Generar lista de feriados para inyectar en el contexto
    import holidays
    year_actual = get_now_chile().year
    feriados_cl = holidays.country_holidays('CL', years=year_actual)
    feriados_str = ", ".join([f"{fecha.strftime('%Y-%m-%d')} ({nombre})" for fecha, nombre in sorted(feriados_cl.items())])

    # Contexto del sistema
    system_prompt = (
        "Eres el Asistente Ejecutivo e Inteligencia Operativa de Nexora, un experto en organización, atención al cliente y generación de ventas. "
        "Tu objetivo es ayudar a los clientes a agendar de la manera más rápida posible, maximizar la operatividad de la empresa y detectar oportunidades de venta (upselling/cross-selling).\n\n"
        "Reglas de Actuación:\n"
        "1. PROACTIVIDAD AL AGENDAR: No hagas preguntas abiertas. Ofrece opciones directas (ej: '¿Te parece bien mañana a las 10:00 AM?').\n"
        "2. GENERACIÓN DE VENTAS: Sugiere de forma elegante un servicio complementario o premium que agregue valor.\n"
        "3. OPERATIVIDAD B2B: Sé extremadamente eficiente, cortés y resolutivo. Respuestas cortas, ideales para leerse en WhatsApp.\n"
        "4. PROTOCOLO DE REGISTRO: Cuando tengas confirmación de fecha y motivo, incluye al final EXACTAMENTE: [AGENDAR: YYYY-MM-DD HH:MM | Motivo].\n"
        "5. PANEL DE ADMIN: Si te inyectan datos de negocio, responde como un analista experto dando recomendaciones.\n"
        f"6. REGLA DE DISPONIBILIDAD: Solo se agenda de Lunes a Viernes. No agendes en fin de semana ni feriados: {feriados_str}.\n"
        "7. FORMATO DE TEXTO ESTRICTO: ESTÁ TOTALMENTE PROHIBIDO usar Markdown. Jamás uses asteriscos (*) ni símbolos raros para negritas o cursivas. Escribe 100% en texto plano.\n"
        "8. ESTILO, CONCISIÓN Y TONO: Sé extremadamente cálido, encantador ('lindo') y directo. Resume la información de las citas en una sola oración fluida y natural. Omite cálculos robóticos innecesarios (como 'asumiendo una duración... el total es'). Ve directo al punto con amabilidad.\n"
        "Responde siempre en español, con un tono entusiasta, profesional y muy servicial."
    )
    
    system_prompt += contexto_datos
    
    payload = {
        "model": "mercury-2",
        "messages": [
            {"role": "system", "content": system_prompt}
        ]
    }
    
    # Inyectar historial si existe
    if telefono:
        if telefono not in historial_global:
            historial_global[telefono] = []
        payload["messages"].extend(historial_global[telefono][-6:])
        
    payload["messages"].append({"role": "user", "content": mensaje})
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            data = res.json()
            respuesta_ia = data["choices"][0]["message"]["content"]
            
            # Guardar en el historial
            if telefono:
                historial_global[telefono].append({"role": "user", "content": mensaje})
                historial_global[telefono].append({"role": "assistant", "content": respuesta_ia})
            
            # Parsear intención de agendamiento real (Fase 2)
            import re
            match = re.search(r'\[AGENDAR:\s*(.*?)\s*\|\s*(.*?)\]', respuesta_ia)
            if match and db and telefono:
                fecha_str = match.group(1).strip()
                motivo_marca = match.group(2).strip()
                
                try:
                    # Intentar parsear fecha
                    # Como la IA a veces puede enviar un formato imperfecto, hacemos lo posible
                    fecha_inicio = datetime.strptime(fecha_str, "%Y-%m-%d %H:%M")
                except:
                    # Fallback a hoy si la IA formatea mal
                    fecha_inicio = get_now_chile() + timedelta(days=1)
                
                # Validar doblemente en backend si es fin de semana o feriado
                import holidays
                if fecha_inicio.weekday() >= 5 or fecha_inicio.date() in holidays.country_holidays('CL'):
                    # En lugar de guardar en BD, corregimos la respuesta de la IA
                    respuesta_ia = "Lo siento, acabo de notar que ese día es fin de semana o feriado. Por favor, indícame otro día hábil (lunes a viernes) para agendar tu cita."
                else:
                    # Ejecutar agendamiento real en Base de Datos
                    agendar_cita_ia(db=db, tenant_id=tenant_id, telefono=telefono, fecha_inicio=fecha_inicio, marca=motivo_marca)
                    
                    # Limpiar la respuesta visual para el usuario
                    respuesta_ia = re.sub(r'\[AGENDAR:.*?\]', '', respuesta_ia).strip()
                
            return respuesta_ia
        else:
            return f"Error en la inteligencia artificial (Código {res.status_code}): {res.text}"
    except Exception as e:
        return f"Error de conexión con la IA: {str(e)}"
