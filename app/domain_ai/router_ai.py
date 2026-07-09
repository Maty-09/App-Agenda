from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.domain_ai import services

router = APIRouter(prefix="/admin/ai", tags=["ai_analytics"])

from app.core.auth_deps import verificar_login

def verificar_sesion_admin(request: Request):
    try:
        return verificar_login(request)
    except HTTPException:
        return None

@router.get("/insights")
async def obtener_insights(request: Request, db: Session = Depends(get_db)):
    """API Endpoint para que el Frontend cargue los clientes inactivos asíncronamente"""
    if not verificar_sesion_admin(request):
        raise HTTPException(status_code=401, detail="No autorizado")
        
    inactivos = services.detectar_clientes_inactivos(db, tenant_id="default", umbral_meses=3)
    return JSONResponse(content={"status": "ok", "data": inactivos})

@router.post("/chat")
async def chat_copiloto(request: Request, mensaje: str = Form(...), db: Session = Depends(get_db)):
    """API Endpoint para interactuar con el Copiloto AI"""
    if not verificar_sesion_admin(request):
        raise HTTPException(status_code=401, detail="No autorizado")
        
    respuesta = services.chat_ia(mensaje, db=db, telefono="WEB-CHAT")
    
    # Comprobar si se agendó para recargar la UI
    import re
    agendado = False
    if "¡Perfecto! He registrado" in respuesta or "agendado" in respuesta.lower() or "confirmado" in respuesta.lower():
        # En el service se quitó la etiqueta [AGENDAR] de la respuesta visual,
        # pero podemos saber si se agendó si la IA responde positivamente.
        # Otra opción es que la IA indique que se recargue.
        agendado = True
        
    return JSONResponse(content={"status": "ok", "reply": respuesta, "agendado": agendado})
