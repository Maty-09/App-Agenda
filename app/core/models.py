from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Enum,Time, ForeignKey, Date, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base
import enum
import pytz


def get_now_chile():
    return datetime.now(pytz.timezone("America/Santiago")).replace(tzinfo=None)


class Tenant(Base):
    __tablename__ = "tenants"
    id = Column(String, primary_key=True, index=True, default="default")
    nombre_empresa = Column(String, nullable=False, default="Nexora Principal")
    config_json = Column(String, nullable=True) # JSON para configs específicas
    
    # Monetización (Stripe)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    plan_actual = Column(String, default="Starter") # Starter, Pro, Business
    estado_suscripcion = Column(String, default="activa") # activa, impaga, cancelada
    
    agendamientos = relationship("Agendamiento", back_populates="tenant")

class DiaBloqueado(Base):
    __tablename__ = "dias_bloqueados"
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    fecha = Column(Date, unique=True, nullable=False)
    motivo = Column(String, nullable=True)

class TipoServicio(str, enum.Enum):
    especializado = "especializado"
    domicilio_taller = "domicilio_taller"

class Cliente(Base):
    __tablename__ = "clientes"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    rut = Column(String, nullable=False, unique=True, index=True)
    nombre = Column(String, nullable=False)
    apellido = Column(String, nullable=False)
    telefono = Column(String, nullable=False)
    correo = Column(String, nullable=False)
    etiquetas = Column(String, nullable=True) # JSON simplificado por ahora

    agendamientos = relationship("Agendamiento", back_populates="cliente")
    timeline = relationship("TimelineEvent", back_populates="cliente")
    tareas = relationship("Tarea", back_populates="cliente")
    tenant = relationship("Tenant")

class TimelineEvent(Base):
    __tablename__ = "timeline_events"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False)
    tipo_evento = Column(String, nullable=False) # RESERVA, EMAIL, WHATSAPP, NOTA
    metadata_json = Column(String, nullable=True)
    creado_en = Column(DateTime, default=get_now_chile)

    cliente = relationship("Cliente", back_populates="timeline")

class Usuario(Base):
    __tablename__ = "usuarios"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    nombre = Column(String, nullable=False)
    email = Column(String, nullable=False, unique=True, index=True)
    password_hash = Column(String, nullable=False)
    rol = Column(String, default="tecnico") # admin, tecnico, asesor

    tareas_asignadas = relationship("Tarea", back_populates="asignado")
    tenant = relationship("Tenant")

class Tarea(Base):
    __tablename__ = "tareas"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    asignado_a = Column(Integer, ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id", ondelete="CASCADE"), nullable=True)
    titulo = Column(String, nullable=False)
    descripcion = Column(String, nullable=True)
    estado = Column(String, default="Pendiente") # Pendiente, En progreso, En revisión, Completada, Cancelada
    prioridad = Column(String, default="Media") # Baja, Media, Alta, Crítica
    observaciones = Column(String, nullable=True)
    comentarios = Column(String, nullable=True) # Podríamos usar JSON o texto largo
    
    fecha_limite = Column(DateTime, nullable=True)
    fecha_inicio = Column(DateTime, nullable=True)
    fecha_cierre = Column(DateTime, nullable=True)
    creado_en = Column(DateTime, default=get_now_chile)

    asignado = relationship("Usuario", back_populates="tareas_asignadas")
    cliente = relationship("Cliente", back_populates="tareas")

class Agendamiento(Base):
    __tablename__ = "agendamientos"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=True) # True por ahora para compatibilidad hacia atrás
    
    #Cliente (Campos legacy, mantener por ahora pero se usará Cliente en el futuro)
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
    duracion_horas = Column(Integer, default=2)
    hora = Column(Time, nullable=True)
    equipo = Column(String, nullable=False)
    subtipo = Column(String, nullable=True)  
    utm_link = Column(String, nullable=True)
    utm_source_real = Column(String, nullable=True)
    nota_interna = Column(String, nullable=True)
    boton_enviado = Column(Boolean, default=False, server_default='0')
    nota_compartida = Column(String, nullable=True)
    estado = Column(String, default="pendiente") # activa | cancelada
    razon_estado = Column(String, nullable=True) # Para detallar motivo de pendiente o cancelación (Fase 1)
    fecha_cancelacion = Column(DateTime, nullable= True)
    respuestas_dinamicas = relationship("RespuestaCampo", back_populates="agendamiento")
    tenant = relationship("Tenant", back_populates="agendamientos")
    cliente = relationship("Cliente", back_populates="agendamientos")

    utm = relationship("UTMRegistro", back_populates="agendamiento", uselist=False, cascade="all, delete-orphan")
    notificaciones = relationship("NotificacionAgendamiento", back_populates="agendamiento", cascade="all, delete-orphan")


class NotificacionAgendamiento(Base):
    __tablename__ = "notificaciones_agendamiento"
    __table_args__ = (UniqueConstraint("agendamiento_id", "tipo", "canal", name="uq_notificacion_agendamiento_tipo_canal"),)

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, index=True)
    agendamiento_id = Column(Integer, ForeignKey("agendamientos.id", ondelete="CASCADE"), nullable=False, index=True)
    tipo = Column(String, nullable=False)
    canal = Column(String, nullable=False)
    enviado_en = Column(DateTime, default=get_now_chile, nullable=False)
    detalle_error = Column(String, nullable=True)

    agendamiento = relationship("Agendamiento", back_populates="notificaciones")



class UTMRegistro(Base):
    __tablename__ = "utm_registros"
    
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
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
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
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
    tenant_id = Column(String, ForeignKey("tenants.id"), nullable=False, default="default")
    agendamiento_id = Column(Integer, ForeignKey("agendamientos.id", ondelete="CASCADE"))
    campo_id = Column(Integer, ForeignKey("campos_formulario.id"))
    valor = Column(String)

    # El back_populates debe apuntar al nombre de la relación en Agendamiento
    agendamiento = relationship("Agendamiento", back_populates="respuestas_dinamicas")
    campo = relationship("CampoFormulario", back_populates="respuestas")


