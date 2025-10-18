from sqlalchemy.orm import Session
from app import models, schemas
from datetime import time

def verificar_disponibilidad(db: Session, agendamiento: schemas.AgendamientoCreate) -> bool:
    inicio = agendamiento.fecha_inicio
    termino = agendamiento.fecha_termino

    # Verificar colación (solo para especializado)
    if agendamiento.tipo_servicio == schemas.TipoServicio.especializado:
        if (inicio.time() < time(8, 0)) or (termino.time() > time(16, 0)):
            return False
        if (inicio.time() < time(13, 0) and termino.time() > time(12, 0)):
            return False

    # Para todos: verificar si ya hay una cita en ese rango
    citas_existentes = db.query(models.Agendamiento).filter(
        models.Agendamiento.fecha_inicio < termino,
        models.Agendamiento.fecha_termino > inicio,
        models.Agendamiento.tipo_servicio == agendamiento.tipo_servicio
    ).all()

    return len(citas_existentes) == 0
