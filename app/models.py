from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum,Time, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum

class TipoServicio(str, enum.Enum):
    especializado = "especializado"
    domicilio_taller = "domicilio_taller"

class Agendamiento(Base):
    __tablename__ = "agendamientos"

    id = Column(Integer, primary_key=True, index=True)
    
    #Cliente
    rut = Column(String, nullable=False)
    tipo_servicio = Column(Enum(TipoServicio), nullable=False)
    nombre = Column(String, nullable=False)
    apellido = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    correo = Column(String, nullable=False)
    #Vivienda
    direccion = Column(String, nullable=True)
    tipo_vivienda = Column(String, nullable=False)
    #Vehiculo
    marca = Column(String, nullable=False)
    modelo = Column(String, nullable=False)
    patente = Column(String, nullable=False)
    kilometraje = Column(Integer, nullable=True)
    #Agenda
    fecha_inicio = Column(DateTime, nullable=False)
    fecha_termino = Column(DateTime, nullable=False)
    creado_en = Column(DateTime, server_default=func.now())
    duracion_horas = Column(Integer, nullable=False)
    hora = Column(Time, nullable=True)
    equipo = Column(String, nullable=False)
    subtipo = Column(String, nullable=True)  
    utm_link = Column(String, nullable=True)
    utm_source_real = Column(String, nullable=True)
    nota_interna = Column(String, nullable=True)
    estado = Column(String, default="activa") # activa | cancelada
    fecha_cancelacion = Column(DateTime, nullable= True)

    utm = relationship("UTMRegistro", back_populates="agendamiento", uselist=False, cascade="all, delete-orphan")



class UTMRegistro(Base):
    __tablename__ = "utm_registros"
    
    id = Column(Integer, primary_key=True, index=True)
    agendamiento_id = Column(Integer, ForeignKey("agendamientos.id", ondelete="CASCADE"), nullable=False)
    
    utm_source = Column(String, nullable=True)
    utm_medium = Column(String)
    utm_campaign = Column(String)
    fecha_registro = Column(DateTime, default=datetime.utcnow)
    ip = Column(String, nullable=True)
    user_agent = Column(String, nullable=True)

    agendamiento = relationship("Agendamiento", back_populates="utm")
