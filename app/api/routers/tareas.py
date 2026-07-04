from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core import models, schemas
from app.api import deps

router = APIRouter()

@router.get("/", response_model=List[schemas.TareaOut])
def get_tareas(
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user)
):
    """Obtiene todas las tareas del tenant actual."""
    tareas = db.query(models.Tarea).filter(models.Tarea.tenant_id == current_user.tenant_id).all()
    return tareas

@router.post("/", response_model=schemas.TareaOut, status_code=status.HTTP_201_CREATED)
def create_tarea(
    tarea: schemas.TareaCreate,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user)
):
    """Crea una nueva tarea."""
    nueva_tarea = models.Tarea(
        **tarea.model_dump(),
        tenant_id=current_user.tenant_id
    )
    db.add(nueva_tarea)
    db.commit()
    db.refresh(nueva_tarea)
    return nueva_tarea

@router.put("/{tarea_id}", response_model=schemas.TareaOut)
def update_tarea(
    tarea_id: int,
    tarea_in: schemas.TareaUpdate,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user)
):
    """Actualiza estado o detalles de una tarea (Drag & Drop en Kanban)."""
    tarea = db.query(models.Tarea).filter(
        models.Tarea.id == tarea_id,
        models.Tarea.tenant_id == current_user.tenant_id
    ).first()
    
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    
    update_data = tarea_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(tarea, field, value)
        
    db.commit()
    db.refresh(tarea)
    return tarea

@router.delete("/{tarea_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tarea(
    tarea_id: int,
    db: Session = Depends(deps.get_db),
    current_user: models.Usuario = Depends(deps.get_current_active_user)
):
    tarea = db.query(models.Tarea).filter(
        models.Tarea.id == tarea_id,
        models.Tarea.tenant_id == current_user.tenant_id
    ).first()
    
    if not tarea:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
        
    db.delete(tarea)
    db.commit()
    return None
