from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
from typing import Optional

from app.core.database import get_db
from app.domain_team import crud_team
from app.core import models

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

router = APIRouter(prefix="/admin/tareas", tags=["team_tareas"])

def verificar_sesion_admin(request: Request):
    if request.cookies.get("admin_session") != "valid":
        return False
    return True

@router.get("", response_class=HTMLResponse)
async def ver_panel_tareas(request: Request, db: Session = Depends(get_db)):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    tareas = crud_team.get_tareas_pendientes(db=db, tenant_id="default")
    usuarios = crud_team.get_usuarios(db=db, tenant_id="default")
    
    # También obtenemos los clientes para el selector al crear tarea (opcional)
    clientes = db.query(models.Cliente).filter(models.Cliente.tenant_id == "default").all()
    
    return templates.TemplateResponse("admin/team_tareas.html", {
        "request": request,
        "tareas": tareas,
        "usuarios": usuarios,
        "clientes": clientes
    })

@router.post("")
async def crear_nueva_tarea(
    request: Request, 
    titulo: str = Form(...),
    descripcion: str = Form(None),
    asignado_a: Optional[int] = Form(None),
    cliente_id: Optional[int] = Form(None),
    db: Session = Depends(get_db)
):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    crud_team.crear_tarea(
        db=db, 
        tenant_id="default", 
        titulo=titulo, 
        descripcion=descripcion,
        asignado_a=asignado_a,
        cliente_id=cliente_id
    )
    
    # Si viene desde la ficha del cliente, volver allá
    if cliente_id and "clientes" in request.headers.get("referer", ""):
        return RedirectResponse(url=f"/admin/clientes/{cliente_id}", status_code=303)
        
    return RedirectResponse(url="/admin/tareas", status_code=303)

@router.post("/{tarea_id}/completar")
async def completar_tarea(request: Request, tarea_id: int, db: Session = Depends(get_db)):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    crud_team.marcar_tarea_completada(db=db, tenant_id="default", tarea_id=tarea_id)
    
    # Volver de donde vino
    referer = request.headers.get("referer", "/admin/tareas")
    return RedirectResponse(url=referer, status_code=303)
