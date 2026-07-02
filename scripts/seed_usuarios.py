import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Asegurar path correcto
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from app.core import models

load_dotenv()
PG_URL = os.getenv("DATABASE_URL")
if PG_URL and PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(PG_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def seed_usuarios():
    db = SessionLocal()
    try:
        # Verificar si ya existe
        admin = db.query(models.Usuario).filter(models.Usuario.email == "admin@nexora.cl").first()
        if not admin:
            admin = models.Usuario(
                tenant_id="default",
                nombre="Administrador Principal",
                email="admin@nexora.cl",
                password_hash="hashed_1234", # Simulado por ahora
                rol="admin"
            )
            db.add(admin)
            
            tecnico = models.Usuario(
                tenant_id="default",
                nombre="Técnico Cristhian",
                email="cristhian@nexora.cl",
                password_hash="hashed_1234",
                rol="tecnico"
            )
            db.add(tecnico)
            
            db.commit()
            print("✅ Usuarios iniciales insertados.")
        else:
            print("⚠️ Los usuarios ya existían.")
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_usuarios()
