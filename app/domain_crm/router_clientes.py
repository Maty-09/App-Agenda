from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import json

from app.core.database import get_db
from app.domain_crm import crud_clientes
from app.core import models

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

router = APIRouter(prefix="/admin", tags=["crm_clientes"])

def verificar_sesion_admin(request: Request):
    if request.cookies.get("admin_session") != "valid":
        return False
    return True

@router.get("/clientes", response_class=HTMLResponse)
async def ver_directorio_clientes(request: Request, search: str = None, db: Session = Depends(get_db)):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    clientes = crud_clientes.get_clientes(db=db, tenant_id="default", search=search)
    return templates.TemplateResponse("admin/crm_clientes.html", {
        "request": request,
        "clientes": clientes,
        "search": search
    })

@router.get("/clientes/{cliente_id}", response_class=HTMLResponse)
async def ver_ficha_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db)):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    cliente = crud_clientes.get_cliente(db=db, cliente_id=cliente_id, tenant_id="default")
    if not cliente:
        return RedirectResponse(url="/admin/clientes", status_code=303)
        
    timeline = crud_clientes.get_timeline(db=db, cliente_id=cliente_id, tenant_id="default")
    
    # Preprocesar JSON para jinja
    eventos_procesados = []
    for evt in timeline:
        meta = {}
        if evt.metadata_json:
            try:
                meta = json.loads(evt.metadata_json)
            except:
                pass
        eventos_procesados.append({"id": evt.id, "tipo": evt.tipo_evento, "fecha": evt.creado_en, "meta": meta})
        
    return templates.TemplateResponse("admin/crm_ficha.html", {
        "request": request,
        "cliente": cliente,
        "timeline": eventos_procesados
    })

@router.post("/clientes/{cliente_id}/notas")
async def agregar_nota_timeline(request: Request, cliente_id: int, texto_nota: str = Form(...), db: Session = Depends(get_db)):
    if not verificar_sesion_admin(request):
        return RedirectResponse(url="/admin/login", status_code=303)
        
    crud_clientes.add_timeline_nota(db=db, cliente_id=cliente_id, tenant_id="default", nota=texto_nota)
    return RedirectResponse(url=f"/admin/clientes/{cliente_id}", status_code=303)
