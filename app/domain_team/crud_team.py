from datetime import datetime
from sqlalchemy.orm import Session
from app.core import models

ESTADOS_KANBAN = ["Pendiente", "En progreso", "En revisión", "Completada"]

def get_usuarios(db: Session, tenant_id: str):
    return db.query(models.Usuario).filter(models.Usuario.tenant_id == tenant_id).all()

def crear_tarea(db: Session, tenant_id: str, titulo: str, descripcion: str, asignado_a: int = None,
                 cliente_id: int = None, fecha_limite=None, fecha_inicio=None, prioridad: str = "Media"):
    tarea = models.Tarea(
        tenant_id=tenant_id,
        titulo=titulo,
        descripcion=descripcion,
        asignado_a=asignado_a,
        cliente_id=cliente_id,
        fecha_limite=fecha_limite,
        fecha_inicio=fecha_inicio,
        prioridad=prioridad or "Media"
    )
    db.add(tarea)
    db.commit()
    db.refresh(tarea)

    # Si la tarea está asociada a un cliente, registrar en el Timeline
    if cliente_id:
        import json
        from app.domain_crm.crud_clientes import add_timeline_nota
        # Alternativamente podríamos crear un tipo de evento 'TAREA', pero para reutilizar:
        evento = models.TimelineEvent(
            tenant_id=tenant_id,
            cliente_id=cliente_id,
            tipo_evento="NOTA",
            metadata_json=json.dumps({"texto": f"Tarea creada: {titulo}"})
        )
        db.add(evento)
        db.commit()

    return tarea

def get_tareas_kanban(db: Session, tenant_id: str):
    """Tareas activas (no canceladas) del tenant, agrupadas por columna de estado."""
    tareas = db.query(models.Tarea).filter(
        models.Tarea.tenant_id == tenant_id,
        models.Tarea.estado != "Cancelada"
    ).order_by(models.Tarea.fecha_limite.asc().nullslast(), models.Tarea.id.desc()).all()

    columnas = {estado: [] for estado in ESTADOS_KANBAN}
    for tarea in tareas:
        columnas.setdefault(tarea.estado or "Pendiente", []).append(tarea)
    return columnas

def get_tareas_pendientes(db: Session, tenant_id: str):
    return db.query(models.Tarea).filter(
        models.Tarea.tenant_id == tenant_id,
        models.Tarea.estado == "Pendiente"
    ).order_by(models.Tarea.id.desc()).all()

def get_tareas_por_cliente(db: Session, tenant_id: str, cliente_id: int):
    return db.query(models.Tarea).filter(
        models.Tarea.tenant_id == tenant_id,
        models.Tarea.cliente_id == cliente_id,
        models.Tarea.estado != "Cancelada"
    ).order_by(models.Tarea.id.desc()).all()

def marcar_tarea_completada(db: Session, tenant_id: str, tarea_id: int):
    tarea = db.query(models.Tarea).filter(
        models.Tarea.tenant_id == tenant_id,
        models.Tarea.id == tarea_id
    ).first()

    if tarea:
        tarea.estado = "Completada"
        db.commit()
        
        # Registrar en timeline si tiene cliente
        if tarea.cliente_id:
            import json
            evento = models.TimelineEvent(
                tenant_id=tenant_id,
                cliente_id=tarea.cliente_id,
                tipo_evento="NOTA",
                metadata_json=json.dumps({"texto": f"Tarea completada: {tarea.titulo}"})
            )
            db.add(evento)
            db.commit()
            
    return tarea
