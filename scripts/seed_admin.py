import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import models, database, security

def seed_admin():
    db = database.SessionLocal()
    try:
        # Asegurarse de que exista el tenant default
        tenant = db.query(models.Tenant).filter(models.Tenant.id == "default").first()
        if not tenant:
            print("Creando Tenant por defecto...")
            tenant = models.Tenant(id="default", nombre_empresa="Nexora Principal")
            db.add(tenant)
            db.commit()

        # Revisar si existe el admin
        email_admin = "admin@nexora.com"
        admin = db.query(models.Usuario).filter(models.Usuario.email == email_admin).first()
        if not admin:
            print(f"Creando usuario Super Admin: {email_admin}...")
            nuevo_admin = models.Usuario(
                tenant_id="default",
                nombre="Admin Nexora",
                email=email_admin,
                password_hash=security.get_password_hash("admin123"),
                rol="superadmin"
            )
            db.add(nuevo_admin)
            db.commit()
            print("¡Super Admin creado exitosamente!")
            print("Email: admin@nexora.com")
            print("Pass: admin123")
        else:
            print("El usuario Super Admin ya existe. Forzando actualización de contraseña a 'admin123' para pruebas.")
            admin.password_hash = security.get_password_hash("admin123")
            admin.rol = "superadmin"
            db.commit()
            print("Contraseña reseteada a 'admin123'")
            
    finally:
        db.close()

if __name__ == "__main__":
    seed_admin()
