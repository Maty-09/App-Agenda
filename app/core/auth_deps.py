from fastapi import Request, HTTPException
from jose import jwt, JWTError

from app.core import models
from app.core.database import SessionLocal
from app.core.security import SECRET_KEY, ALGORITHM


class CurrentUser:
    def __init__(self, id: int, email: str, tenant_id: str, rol: str):
        self.id = id
        self.email = email
        self.tenant_id = tenant_id
        self.rol = rol


def verificar_login(request: Request) -> CurrentUser:
    """Verifica el JWT (cookie access_token) y retorna el contexto Multi-Tenant del usuario."""
    token = request.cookies.get("access_token")
    if not token or not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="No autenticado")

    token = token.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="Token expirado o inválido")

    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    rol = payload.get("rol")
    email = payload.get("email")

    if user_id is None or tenant_id is None:
        raise HTTPException(status_code=401, detail="Token inválido")

    db = SessionLocal()
    try:
        usuario = db.query(models.Usuario).filter(
            models.Usuario.id == int(user_id),
            models.Usuario.tenant_id == tenant_id,
            models.Usuario.sesion_activa.is_(True),
        ).first()
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
        if not usuario or not tenant:
            raise HTTPException(status_code=401, detail="Sesión finalizada")
        if tenant.estado_suscripcion == "cancelada":
            raise HTTPException(status_code=403, detail="Esta cuenta está desactivada")
    finally:
        db.close()

    return CurrentUser(id=int(user_id), email=email, tenant_id=tenant_id, rol=rol)
