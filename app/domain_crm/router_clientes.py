from fastapi import APIRouter, Request, Depends, Form, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from pathlib import Path
import json

from app.core.database import get_db
from app.domain_crm import crud_clientes
from app.core import models
from app.core.auth_deps import CurrentUser, verificar_login

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=[str(BASE_DIR / "app" / "templates"), str(BASE_DIR / "templates")])

router = APIRouter(prefix="/admin", tags=["crm_clientes"])

@router.get("/clientes", response_class=HTMLResponse)
async def ver_directorio_clientes(request: Request, search: str = None, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    clientes = crud_clientes.get_clientes(db=db, tenant_id=cred.tenant_id, search=search)
    return templates.TemplateResponse("admin/crm_clientes.html", {
        "request": request,
        "clientes": clientes,
        "search": search,
        "current_user": cred
    })

@router.get("/clientes/{cliente_id}", response_class=HTMLResponse)
async def ver_ficha_cliente(request: Request, cliente_id: int, db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    cliente = crud_clientes.get_cliente(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id)
    if not cliente:
        return RedirectResponse(url="/admin/clientes", status_code=303)

    timeline = crud_clientes.get_timeline(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id)

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
        "timeline": eventos_procesados,
        "current_user": cred
    })

@router.post("/clientes/{cliente_id}/notas")
async def agregar_nota_timeline(request: Request, cliente_id: int, texto_nota: str = Form(...), db: Session = Depends(get_db), cred: CurrentUser = Depends(verificar_login)):
    crud_clientes.add_timeline_nota(db=db, cliente_id=cliente_id, tenant_id=cred.tenant_id, nota=texto_nota)
    return RedirectResponse(url=f"/admin/clientes/{cliente_id}", status_code=303)
