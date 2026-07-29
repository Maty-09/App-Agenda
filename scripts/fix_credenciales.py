import sys
import os
import secrets
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import models, database, security


def fix_credenciales():
    db = database.SessionLocal()
    try:
        # 1. Eliminar duplicado admin@noren.cl (sin tareas asignadas, seguro de borrar)
        duplicado = db.query(models.Usuario).filter(models.Usuario.email == "admin@noren.cl").first()
        if duplicado:
            db.delete(duplicado)
            db.commit()
            print(f"Eliminado usuario duplicado: admin@noren.cl (id={duplicado.id})")
        else:
            print("admin@noren.cl no existe, nada que eliminar.")

        # 2. Confirmar admin@noren.com con password admin123 (ya tenía hash válido)
        admin = db.query(models.Usuario).filter(models.Usuario.email == "admin@noren.com").first()
        if admin:
            admin.password_hash = security.get_password_hash("admin123")
            admin.rol = "superadmin"
            db.commit()
            print("admin@noren.com: password confirmada/re-hasheada a 'admin123'")
        else:
            print("ADVERTENCIA: admin@noren.com no existe")

        # 3. Resetear cristhian@noren.cl con password temporal
        cristhian = db.query(models.Usuario).filter(models.Usuario.email == "cristhian@noren.cl").first()
        if cristhian:
            temp_password = secrets.token_urlsafe(9)
            cristhian.password_hash = security.get_password_hash(temp_password)
            db.commit()
            print(f"cristhian@noren.cl: password temporal asignada -> {temp_password}")
        else:
            print("ADVERTENCIA: cristhian@noren.cl no existe")

    finally:
        db.close()


if __name__ == "__main__":
    fix_credenciales()
