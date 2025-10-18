from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from app import models

def verificar_disponibilidad_especializado(db: Session, inicio: datetime, duracion_horas: int) -> bool:
    fin = inicio + timedelta(hours=duracion_horas)

    # Validación de horario laboral
    if not (inicio.hour >= 8 and fin.hour <= 16):
        return False

    # Validación de colación (12:00 a 13:00)
    if (inicio < inicio.replace(hour=13, minute=0) and fin > inicio.replace(hour=12, minute=0)):
        return False

    agendados = db.query(models.Agendamiento).filter(
        models.Agendamiento.tipo_servicio == "especializado",
        models.Agendamiento.fecha_inicio < fin,
        models.Agendamiento.fecha_termino > inicio
    ).all()

    return len(agendados) == 0


def verificar_disponibilidad(db: Session, tipo_servicio: str, inicio: datetime, duracion_horas: int) -> bool:
    fin = inicio + timedelta(hours=duracion_horas)

    if tipo_servicio == "especializado":
        # Validar horario laboral
        if not (8 <= inicio.hour < 16 and fin.hour <= 16):
            return False

        # Evitar hora de colación (12:00 a 13:00)
        colacion_inicio = inicio.replace(hour=12, minute=0)
        colacion_fin = inicio.replace(hour=13, minute=0)
        if inicio < colacion_fin and fin > colacion_inicio:
            return False

    elif tipo_servicio in ["taller", "domicilio"]:
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
