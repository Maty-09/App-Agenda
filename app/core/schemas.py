from pydantic import BaseModel, EmailStr
from datetime import datetime
from enum import Enum

class TipoServicio(str, Enum):
    especializado = "especializado"
    domicilio_taller = "domicilio_taller"

class AgendamientoBase(BaseModel):
    tipo_servicio: TipoServicio
    nombre: str
    apellido: str
    correo: EmailStr
    telefono: str
    patente: str
    fecha_inicio: datetime
    fecha_termino: datetime

class AgendamientoCreate(AgendamientoBase):
    tipo_servicio: str
    nombre: str
    apellido: str
    correo: str
    telefono: str
    patente: str
    fecha_inicio: datetime
    fecha_termino: datetime
    duracion_horas: int  # 👈 Agrega esto s

class AgendamientoOut(AgendamientoBase):
    id: int
    creado_en: datetime

    class Config:
        from_attributes = True

# --- Tareas (Kanban) ---
from typing import Optional

class TareaBase(BaseModel):
    titulo: str
    descripcion: Optional[str] = None
    estado: str = "Pendiente"
    prioridad: str = "Media"
    observaciones: Optional[str] = None
    comentarios: Optional[str] = None
    fecha_limite: Optional[datetime] = None
    fecha_inicio: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    asignado_a: Optional[int] = None
    cliente_id: Optional[int] = None

class TareaCreate(TareaBase):
    pass

class TareaUpdate(BaseModel):
    titulo: Optional[str] = None
    descripcion: Optional[str] = None
    estado: Optional[str] = None
    prioridad: Optional[str] = None
    observaciones: Optional[str] = None
    comentarios: Optional[str] = None
    fecha_limite: Optional[datetime] = None
    fecha_inicio: Optional[datetime] = None
    fecha_cierre: Optional[datetime] = None
    asignado_a: Optional[int] = None

class TareaOut(TareaBase):
    id: int
    tenant_id: str
    creado_en: datetime

    class Config:
        from_attributes = True
