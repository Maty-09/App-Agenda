import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import models, database, security

def seed_demo():
    db = database.SessionLocal()
    try:
        # Asegurarse de que exista el tenant demo
        tenant = db.query(models.Tenant).filter(models.Tenant.id == "demo-lunes-viernes").first()
        if not tenant:
            print("Creando Tenant Demo...")
            tenant = models.Tenant(id="demo-lunes-viernes", nombre_empresa="Demo Noren (Lunes a Viernes)")
            db.add(tenant)
            db.commit()

        # Crear o actualizar usuario demo
        email_demo = "demo@noren.app"
        demo_user = db.query(models.Usuario).filter(models.Usuario.email == email_demo).first()
        if not demo_user:
            print(f"Creando usuario Demo: {email_demo}...")
            nuevo_demo = models.Usuario(
                tenant_id="demo-lunes-viernes",
                nombre="Usuario Demo Noren",
                email=email_demo,
                password_hash=security.get_password_hash("demo123"),
                rol="admin"
            )
            db.add(nuevo_demo)
            db.commit()
            print("¡Usuario Demo creado exitosamente!")
        else:
            print("El usuario Demo ya existe. Actualizando contraseña a 'demo123'...")
            demo_user.password_hash = security.get_password_hash("demo123")
            demo_user.rol = "admin"
            db.commit()
            print("Contraseña reseteada a 'demo123'")

        print(f"Email Demo: {email_demo}")
        print("Pass Demo: demo123")
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo()
