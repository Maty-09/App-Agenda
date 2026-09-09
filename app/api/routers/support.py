"""Endpoints del asistente de soporte, disponibles solo a usuarios autenticados."""

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core import models
from app.core.auth_deps import CurrentUser, verificar_login
from app.domain_ai.support_service import answer_support_question

router = APIRouter()


@router.post("/chat")
def chat_soporte(
    mensaje: str = Form(..., min_length=1, max_length=1200),
    db: Session = Depends(get_db),
    cred: CurrentUser = Depends(verificar_login),
):
    tenant = db.query(models.Tenant).filter(models.Tenant.id == cred.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="No encontramos la cuenta de este negocio.")
    return JSONResponse(content=answer_support_question(mensaje, tenant, db))
