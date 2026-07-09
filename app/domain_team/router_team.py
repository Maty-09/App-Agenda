from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional
from datetime import datetime

from app.core.database import get_db
from app.domain_team import crud_team
from app.core import models
from app.core.auth_deps import CurrentUser, verificar_login

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=[str(BASE_DIR / "app" / "templates"), str(BASE_DIR / "templates")])

router = APIRouter(prefix="/admin/tareas", tags=["team_tareas"])

@router.get("", response_class=HTMLResponse)
async def ver_panel_tareas(request: Request, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    columnas = crud_team.get_tareas_kanban(db=db, tenant_id=cred.tenant_id)
    usuarios = crud_team.get_usuarios(db=db, tenant_id=cred.tenant_id)

    # También obtenemos los clientes para el selector al crear tarea (opcional)
    clientes = db.query(models.Cliente).filter(models.Cliente.tenant_id == cred.tenant_id).all()

    return templates.TemplateResponse("admin/team_tareas.html", {
        "request": request,
        "columnas": columnas,
        "estados": crud_team.ESTADOS_KANBAN,
        "usuarios": usuarios,
        "clientes": clientes,
        "current_user": cred,
        "hoy": datetime.utcnow()
    })

@router.post("")
async def crear_nueva_tarea(
    request: Request,
    titulo: str = Form(...),
    descripcion: str = Form(None),
    asignado_a: Optional[int] = Form(None),
    cliente_id: Optional[int] = Form(None),
    prioridad: str = Form("Media"),
    fecha_limite: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login)
):
    fecha_limite_dt = datetime.fromisoformat(fecha_limite) if fecha_limite else None
    crud_team.crear_tarea(
        db=db,
        tenant_id=cred.tenant_id,
        titulo=titulo,
        descripcion=descripcion,
        asignado_a=asignado_a,
        cliente_id=cliente_id,
        prioridad=prioridad,
        fecha_limite=fecha_limite_dt
    )

    # Si viene desde la ficha del cliente, volver allá
    if cliente_id and "clientes" in request.headers.get("referer", ""):
        return RedirectResponse(url=f"/admin/clientes/{cliente_id}", status_code=303)

    return RedirectResponse(url="/admin/tareas", status_code=303)

@router.post("/{tarea_id}/completar")
async def completar_tarea(request: Request, tarea_id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    crud_team.marcar_tarea_completada(db=db, tenant_id=cred.tenant_id, tarea_id=tarea_id)

    # Volver de donde vino
    referer = request.headers.get("referer", "/admin/tareas")
    return RedirectResponse(url=referer, status_code=303)
