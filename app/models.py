from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum,Time, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import enum
import pytz


def get_now_chile():
    return datetime.now(pytz.timezone("America/Santiago")).replace(tzinfo=None)

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
    creado_en = Column(DateTime, default=get_now_chile)
    duracion_horas = Column(Integer, nullable=False)
    hora = Column(Time, nullable=True)
    equipo = Column(String, nullable=False)
    subtipo = Column(String, nullable=True)  
    utm_link = Column(String, nullable=True)
    utm_source_real = Column(String, nullable=True)
    nota_interna = Column(String, nullable=True)
    nota_compartida = Column(String, nullable=True)
    estado = Column(String, default="pendiente") # activa | cancelada
    fecha_cancelacion = Column(DateTime, nullable= True)
    respuestas_dinamicas = relationship("RespuestaCampo", back_populates="agendamiento")


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


class CampoFormulario(Base):
    __tablename__ = "campos_formulario"  # <--- Verifica que el nombre sea este

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    tipo_campo = Column(String, default="text")
    opciones = Column(String, nullable=True)
    orden = Column(Integer, default=0)
    activo = Column(Boolean, default=True)
    obligatorio = Column(Boolean, default=True)
    tipo_servicio = Column(String, nullable=True) # taller, domicilio o ambos
    subtipo_servicio = Column(String, nullable=True)
    es_sistema = Column(Boolean, default=False) # True para RUT, Nombre, etc.
    nombre_tecnico = Column(String, nullable=True)

    # Relación hacia las respuestas
    respuestas = relationship("RespuestaCampo", back_populates="campo")

class RespuestaCampo(Base):
    __tablename__ = "respuestas_campos"
    id = Column(Integer, primary_key=True, index=True)
    agendamiento_id = Column(Integer, ForeignKey("agendamientos.id", ondelete="CASCADE"))
    campo_id = Column(Integer, ForeignKey("campos_formulario.id"))
    valor = Column(String)

    # El back_populates debe apuntar al nombre de la relación en Agendamiento
    agendamiento = relationship("Agendamiento", back_populates="respuestas_dinamicas")
    campo = relationship("CampoFormulario", back_populates="respuestas")


