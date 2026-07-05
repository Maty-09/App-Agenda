from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import jwt
from app.core import security, models, database
from pydantic import ValidationError

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/login"
)

def get_db():
    db = database.SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_current_user(
    db: Session = Depends(get_db), token: str = Depends(oauth2_scheme)
) -> models.Usuario:
    try:
        payload = jwt.decode(
            token, security.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token no válido")
    except (jwt.PyJWTError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No se pudieron validar las credenciales",
        )
    user = db.query(models.Usuario).filter(models.Usuario.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

def get_current_active_user(
    current_user: models.Usuario = Depends(get_current_user),
) -> models.Usuario:
    return current_user

from typing import List

def require_role(allowed_roles: List[str]):
    def role_checker(current_user: models.Usuario = Depends(get_current_active_user)):
        if current_user.rol not in allowed_roles and current_user.rol != "superadmin":
            raise HTTPException(
                status_code=403, detail="El usuario no tiene privilegios suficientes para esta acción"
            )
        return current_user
    return role_checker

# Dependencias pre-configuradas
get_superadmin = require_role(["superadmin"])
get_admin_empresa = require_role(["admin_empresa"])
get_operador = require_role(["admin_empresa", "operador"])
get_tecnico = require_role(["admin_empresa", "operador", "tecnico"])
