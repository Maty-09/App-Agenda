from sqlalchemy.orm import Session
from app.core import models

def get_clientes(db: Session, tenant_id: str, skip: int = 0, limit: int = 100, search: str = None):
    query = db.query(models.Cliente).filter(models.Cliente.tenant_id == tenant_id)
    if search:
        query = query.filter(
            (models.Cliente.nombre.ilike(f"%{search}%")) |
            (models.Cliente.apellido.ilike(f"%{search}%")) |
            (models.Cliente.rut.ilike(f"%{search}%")) |
            (models.Cliente.correo.ilike(f"%{search}%"))
        )
    return query.order_by(models.Cliente.id.desc()).offset(skip).limit(limit).all()

def get_cliente(db: Session, cliente_id: int, tenant_id: str):
    return db.query(models.Cliente).filter(
        models.Cliente.id == cliente_id,
        models.Cliente.tenant_id == tenant_id
    ).first()

def get_timeline(db: Session, cliente_id: int, tenant_id: str):
    return db.query(models.TimelineEvent).filter(
        models.TimelineEvent.cliente_id == cliente_id,
        models.TimelineEvent.tenant_id == tenant_id
    ).order_by(models.TimelineEvent.creado_en.desc()).all()

def add_timeline_nota(db: Session, cliente_id: int, tenant_id: str, nota: str):
    import json
    evento = models.TimelineEvent(
        tenant_id=tenant_id,
        cliente_id=cliente_id,
        tipo_evento="NOTA",
        metadata_json=json.dumps({"texto": nota})
    )
    db.add(evento)
    db.commit()
    db.refresh(evento)
    return evento
