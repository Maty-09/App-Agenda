from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import timedelta
from app.core import security, models
from app.api import deps

router = APIRouter()

@router.post("/login")
def login_access_token(
    db: Session = Depends(deps.get_db), form_data: OAuth2PasswordRequestForm = Depends()
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    email = form_data.username.strip().lower()
    user = db.query(models.Usuario).filter(models.Usuario.email == email).first()
    if not user or not security.verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Correo o contraseña incorrectos")

    tenant = db.query(models.Tenant).filter(models.Tenant.id == user.tenant_id).first()
    if not tenant or tenant.estado_suscripcion == "cancelada":
        raise HTTPException(status_code=403, detail="Esta cuenta está desactivada")
    
    user.ultima_conexion = models.get_now_chile()
    user.sesion_activa = True
    db.commit()

    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        subject=user.id, 
        rol=user.rol, 
        tenant_id=user.tenant_id, 
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_info": {
            "id": user.id,
            "nombre": user.nombre,
            "email": user.email,
            "rol": user.rol,
            "tenant_id": user.tenant_id
        }
    }
