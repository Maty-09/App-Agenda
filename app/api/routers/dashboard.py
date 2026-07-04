from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from typing import Dict, Any, List
from app.core import models
from app.api import deps
import pytz

router = APIRouter()

CAPACIDAD_DIARIA_MAXIMA = 8 # Configuración futura en Tenant

@router.get("/capacidad", response_model=List[Dict[str, Any]])
def get_control_capacidad(
    dias: int = 30,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user)
):
    """
    Calcula la capacidad futura y disponibilidad de los próximos N días.
    """
    tz = pytz.timezone('America/Santiago')
    hoy = datetime.now(tz).date()
    fecha_fin = hoy + timedelta(days=dias)
    
    # Obtener citas en rango
    citas = db.query(models.Agendamiento).filter(
        models.Agendamiento.tenant_id == current_user.tenant_id,
        models.Agendamiento.fecha_inicio >= hoy,
        models.Agendamiento.fecha_inicio <= fecha_fin
    ).all()
    
    # Obtener bloqueos (feriados/vacaciones)
    bloqueos = db.query(models.DiaBloqueado).filter(
        models.DiaBloqueado.tenant_id == current_user.tenant_id,
        models.DiaBloqueado.fecha >= hoy,
        models.DiaBloqueado.fecha <= fecha_fin
    ).all()
    
    fechas_bloqueadas = {b.fecha for b in bloqueos}
    
    # Mapear conteo por día
    conteo_por_dia = {}
    for cita in citas:
        dia_cita = cita.fecha_inicio.date()
        conteo_por_dia[dia_cita] = conteo_por_dia.get(dia_cita, 0) + 1
        
    resultado = []
    
    for i in range(dias + 1):
        dia_actual = hoy + timedelta(days=i)
        
        # Ignorar domingos o días bloqueados
        if dia_actual.weekday() == 6 or dia_actual in fechas_bloqueadas:
            resultado.append({
                "fecha": dia_actual.isoformat(),
                "capacidad_total": 0,
                "ocupado": 0,
                "disponible": 0,
                "estado": "Cerrado"
            })
            continue
            
        ocupado = conteo_por_dia.get(dia_actual, 0)
        disponible = max(0, CAPACIDAD_DIARIA_MAXIMA - ocupado)
        porcentaje = (ocupado / CAPACIDAD_DIARIA_MAXIMA) * 100 if CAPACIDAD_DIARIA_MAXIMA > 0 else 0
        
        estado = "Libre"
        if porcentaje > 80:
            estado = "Saturado"
        elif porcentaje > 50:
            estado = "Media"
            
        resultado.append({
            "fecha": dia_actual.isoformat(),
            "capacidad_total": CAPACIDAD_DIARIA_MAXIMA,
            "ocupado": ocupado,
            "disponible": disponible,
            "porcentaje_ocupacion": round(porcentaje, 1),
            "estado": estado
        })
        
    return resultado
