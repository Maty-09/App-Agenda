import os
import sys
import json
from datetime import datetime
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

def migrar_crm_retroactivo():
    db = SessionLocal()
    try:
        agendamientos = db.query(models.Agendamiento).all()
        print(f"📦 Procesando {len(agendamientos)} agendamientos existentes...")

        clientes_creados = 0
        timeline_creados = 0
        agendamientos_vinculados = 0

        for agenda in agendamientos:
            # Buscar si el cliente ya existe por RUT
            cliente = db.query(models.Cliente).filter(models.Cliente.rut == agenda.rut).first()
            
            if not cliente:
                # Crear cliente
                cliente = models.Cliente(
                    tenant_id=agenda.tenant_id,
                    rut=agenda.rut,
                    nombre=agenda.nombre,
                    apellido=agenda.apellido,
                    telefono=agenda.telefono,
                    correo=agenda.correo,
                    etiquetas=json.dumps(["Retroactivo"])
                )
                db.add(cliente)
                db.flush() # Para obtener el ID del cliente
                clientes_creados += 1
            
            # Si el agendamiento no está vinculado
            if not agenda.cliente_id:
                agenda.cliente_id = cliente.id
                agendamientos_vinculados += 1
                
                # Crear evento en timeline histórico
                evento = models.TimelineEvent(
                    tenant_id=agenda.tenant_id,
                    cliente_id=cliente.id,
                    tipo_evento="RESERVA",
                    metadata_json=json.dumps({
                        "agendamiento_id": agenda.id,
                        "fecha": str(agenda.fecha_inicio),
                        "estado": agenda.estado,
                        "nota_migracion": "Generado retroactivamente desde historial"
                    }),
                    creado_en=agenda.creado_en
                )
                db.add(evento)
                timeline_creados += 1
                
        db.commit()
        
        # Resetear secuencias si es necesario
        try:
            db.execute("SELECT setval('clientes_id_seq', (SELECT MAX(id) FROM clientes));")
            db.execute("SELECT setval('timeline_events_id_seq', (SELECT MAX(id) FROM timeline_events));")
            db.commit()
        except Exception as e:
            db.rollback()

        print("✅ Migración CRM retroactiva finalizada.")
        print(f"   - Clientes Creados: {clientes_creados}")
        print(f"   - Agendamientos Vinculados: {agendamientos_vinculados}")
        print(f"   - Eventos de Timeline Creados: {timeline_creados}")

    except Exception as e:
        db.rollback()
        print(f"❌ Error en la migración CRM: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    migrar_crm_retroactivo()
