from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum,Time
from sqlalchemy.sql import func
from app.database import Base
import enum

class TipoServicio(str, enum.Enum):
    especializado = "especializado"
    domicilio_taller = "domicilio_taller"

class Agendamiento(Base):
    __tablename__ = "agendamientos"

    id = Column(Integer, primary_key=True, index=True)
    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    nombre = Column(String, nullable=False)
    apellido = Column(String, nullable=False)
    correo = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    patente = Column(String, nullable=False)
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_termino = Column(DateTime, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    duracion_horas = Column(Integer, nullable=False)
    hora = Column(Time, nullable=True)
