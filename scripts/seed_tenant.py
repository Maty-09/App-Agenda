import sys
import os
import argparse
from passlib.context import CryptContext

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.database import SessionLocal
from app.core.models import Tenant, Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def seed_tenant(tenant_id: str, empresa: str, admin_email: str, admin_pass: str):
    db = SessionLocal()
    try:
        # 1. Crear o buscar Tenant
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if not tenant:
            tenant = Tenant(id=tenant_id, nombre_empresa=empresa)
            db.add(tenant)
            db.commit()
            print(f"[OK] Tenant '{empresa}' (ID: {tenant_id}) creado exitosamente.")
        else:
            print(f"[WARN] Tenant '{tenant_id}' ya existe. Omitiendo creación.")

        # 2. Crear o buscar Usuario Admin
        usuario = db.query(Usuario).filter(Usuario.email == admin_email).first()
        if not usuario:
            usuario = Usuario(
                tenant_id=tenant_id,
                nombre="Administrador",
                email=admin_email,
                password_hash=hash_password(admin_pass),
                rol="admin"
            )
            db.add(usuario)
            db.commit()
            print(f"[OK] Usuario Admin '{admin_email}' creado exitosamente para el tenant '{tenant_id}'.")
        else:
            print(f"[WARN] El correo '{admin_email}' ya está registrado.")
            
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sembrar un nuevo Tenant y su Admin en la base de datos.")
    parser.add_argument("--id", required=True, help="ID único del Tenant (ej: 'empresa1')")
    parser.add_argument("--empresa", required=True, help="Nombre de la Empresa")
    parser.add_argument("--email", required=True, help="Correo del administrador")
    parser.add_argument("--password", required=True, help="Contraseña del administrador")
    
    args = parser.parse_args()
    seed_tenant(args.id, args.empresa, args.email, args.password)
