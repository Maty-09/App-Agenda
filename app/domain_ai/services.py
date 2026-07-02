from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta
from app.core import models
import pytz
import requests
import json

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
    cliente = db.query(models.Cliente).filter(models.Cliente.telefono == telefono).first()
    
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
        tipo_servicio="general",
        nombre=cliente.nombre,
        apellido=cliente.apellido,
        telefono=cliente.telefono,
        correo=cliente.correo,
        marca=marca,
        modelo="Por definir",
        patente="WSP-002",
        fecha_inicio=fecha_inicio,
        fecha_termino=fecha_inicio + timedelta(hours=1),
        origen="whatsapp"
    )
    db.add(cita)
    db.commit()
    db.refresh(cita)
    return cita

def chat_ia(mensaje: str, db: Session = None, telefono: str = None) -> str:
    """
    Integración con la API de InceptionLabs. Contextualizada con base de datos si aplica.
    """
    api_key = ***REMOVED***
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
            top_marcas = obtener_top_marcas_agendadas(db, "default")
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
    
    # Contexto del sistema
    system_prompt = (
        "Eres Copiloto Nexora IA, un asistente B2B. "
        "Si el usuario pregunta por métricas, usa los Datos Reales que se te inyectan en este prompt. "
        "Si el usuario quiere agendar, dile que lo has registrado exitosamente y confirma la fecha (simulando que usaste tu tool). "
        "Sé breve, profesional y útil. Responde en español."
    )
    
    system_prompt += contexto_datos
    
    payload = {
        "model": "mercury-2",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": mensaje}
        ]
    }
    
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data["choices"][0]["message"]["content"]
        else:
            return f"Error en la inteligencia artificial (Código {res.status_code}): {res.text}"
    except Exception as e:
        return f"Error de conexión con la IA: {str(e)}"
