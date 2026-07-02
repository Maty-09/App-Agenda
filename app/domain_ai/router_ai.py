from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.domain_ai import services

router = APIRouter(prefix="/admin/ai", tags=["ai_analytics"])

def verificar_sesion_admin(request: Request):
    if request.cookies.get("admin_session") != "valid":
        return False
    return True

@router.get("/insights")
async def obtener_insights(request: Request, db: Session = Depends(get_db)):
    """API Endpoint para que el Frontend cargue los clientes inactivos asíncronamente"""
    if not verificar_sesion_admin(request):
        raise HTTPException(status_code=401, detail="No autorizado")
        
    inactivos = services.detectar_clientes_inactivos(db, tenant_id="default", umbral_meses=3)
    return JSONResponse(content={"status": "ok", "data": inactivos})

@router.post("/chat")
async def chat_copiloto(request: Request, mensaje: str = Form(...)):
    """API Endpoint para interactuar con el Copiloto AI"""
    if not verificar_sesion_admin(request):
        raise HTTPException(status_code=401, detail="No autorizado")
        
    respuesta = services.chat_ia(mensaje)
    return JSONResponse(content={"status": "ok", "reply": respuesta})
