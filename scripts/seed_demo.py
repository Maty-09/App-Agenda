import sys
import os
from datetime import datetime, timedelta
import pytz

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import models, database, security

def seed_demo():
    db = database.SessionLocal()
    tenant_id = "demo-lunes-viernes"
    tz = pytz.timezone("America/Santiago")
    ahora = datetime.now(tz).replace(tzinfo=None)
    
    try:
        # 1. Asegurar Tenant Demo
        tenant = db.query(models.Tenant).filter(models.Tenant.id == tenant_id).first()
        if not tenant:
            print("Creando Tenant Demo...")
            tenant = models.Tenant(id=tenant_id, nombre_empresa="Demo Noren (Lunes a Viernes)")
            db.add(tenant)
            db.commit()

        # 2. Usuario Demo
        email_demo = "demo@noren.app"
        demo_user = db.query(models.Usuario).filter(models.Usuario.email == email_demo).first()
        if not demo_user:
            print(f"Creando usuario Demo: {email_demo}...")
            nuevo_demo = models.Usuario(
                tenant_id=tenant_id,
                nombre="Usuario Demo Noren",
                email=email_demo,
                password_hash=security.get_password_hash("demo123"),
                rol="admin"
            )
            db.add(nuevo_demo)
            db.commit()
        else:
            demo_user.password_hash = security.get_password_hash("demo123")
            demo_user.rol = "admin"
            db.commit()

        # 3. Sembrar Clientes Demo (si no hay)
        cant_clientes = db.query(models.Cliente).filter(models.Cliente.tenant_id == tenant_id).count()
        clientes = []
        if cant_clientes < 5:
            print("Sembrando Clientes Demo...")
            datos_clientes = [
                {"nombre": "Camila", "apellido": "Rojas", "rut": "11.111.111-1", "telefono": "+569700009", "correo": "demo-101@demo.noren.app"},
                {"nombre": "Diego", "apellido": "Mora", "rut": "11.111.111-2", "telefono": "+5697000011", "correo": "demo-102@demo.noren.app"},
                {"nombre": "Elena", "apellido": "Castro", "rut": "11.111.111-3", "telefono": "+5697000113", "correo": "demo-103@demo.noren.app"},
                {"nombre": "Gabriel", "apellido": "Paz", "rut": "11.111.111-4", "telefono": "+5697000114", "correo": "demo-104@demo.noren.app"},
                {"nombre": "Fernanda", "apellido": "Soto", "rut": "11.111.111-5", "telefono": "+5697000115", "correo": "demo-105@demo.noren.app"},
            ]
            for c_data in datos_clientes:
                cli = models.Cliente(tenant_id=tenant_id, **c_data)
                db.add(cli)
                clientes.append(cli)
            db.commit()
            clientes = db.query(models.Cliente).filter(models.Cliente.tenant_id == tenant_id).all()
        else:
            clientes = db.query(models.Cliente).filter(models.Cliente.tenant_id == tenant_id).all()

        # 4. Sembrar Agendamientos Demo (si no hay suficientes)
        cant_agendas = db.query(models.Agendamiento).filter(models.Agendamiento.tenant_id == tenant_id).count()
        if cant_agendas < 10:
            print("Sembrando Agendamientos y Estadisticas Demo...")
            
            marcas = ["Toyota", "Hyundai", "Chevrolet", "Nissan", "Honda"]
            modelos = ["Yaris", "Tucson", "Sail", "Kicks", "Civic"]
            patentes = ["KK-1234", "AA-5678", "BB-9012", "CC-3456", "DD-7890"]
            equipos = ["Equipo Alfa", "Equipo Beta", "Taller Central", "Equipo Movil"]
            subtipos = ["taller", "domicilio", "taller", "domicilio", "taller"]
            
            fechas_offset = [
                ahora + timedelta(hours=2),
                ahora + timedelta(days=1, hours=4),
                ahora + timedelta(days=2, hours=1),
                ahora + timedelta(days=3, hours=5),
                ahora - timedelta(days=1, hours=3),
                ahora - timedelta(days=2, hours=2),
                ahora - timedelta(days=15),
                ahora - timedelta(days=25),
                ahora - timedelta(days=35),
                ahora - timedelta(days=45),
                ahora - timedelta(days=60),
                ahora - timedelta(days=75)
            ]
            
            for i, fecha in enumerate(fechas_offset):
                cli = clientes[i % len(clientes)]
                tipo_serv = "especializado" if i % 2 == 0 else "domicilio_taller"
                ag = models.Agendamiento(
                    tenant_id=tenant_id,
                    cliente_id=cli.id,
                    rut=cli.rut,
                    tipo_servicio=tipo_serv,
                    subtipo=subtipos[i % len(subtipos)],
                    nombre=cli.nombre,
                    apellido=cli.apellido,
                    telefono=cli.telefono,
                    correo=cli.correo,
                    marca=marcas[i % len(marcas)],
                    modelo=modelos[i % len(modelos)],
                    patente=patentes[i % len(patentes)],
                    tipo_vivienda="Casa",
                    equipo=equipos[i % len(equipos)],
                    fecha_inicio=fecha,
                    fecha_termino=fecha + timedelta(hours=1),
                    estado="confirmado" if i % 4 != 0 else ("pendiente" if i % 4 == 1 else "cancelado"),
                    utm_source_real="Google Ads" if i % 2 == 0 else "WhatsApp Directo"
                )
                db.add(ag)
            db.commit()
            print("Agendamientos demo creados con exito.")

        # 5. Sembrar Tareas Kanban Demo (si no hay)
        cant_tareas = db.query(models.Tarea).filter(models.Tarea.tenant_id == tenant_id).count()
        if cant_tareas == 0:
            print("Sembrando Tareas Kanban Demo...")
            tareas_demo = [
                models.Tarea(tenant_id=tenant_id, titulo="Revisar stock de repuestos Toyota", descripcion="Verificar filtros de aceite y bujías", prioridad="Alta", estado="Pendiente", fecha_limite=ahora + timedelta(days=2)),
                models.Tarea(tenant_id=tenant_id, titulo="Mantenimiento preventivo flotilla 1", descripcion="Coordinación de agendamientos semanales", prioridad="Crítica", estado="En progreso", fecha_limite=ahora + timedelta(days=1)),
                models.Tarea(tenant_id=tenant_id, titulo="Verificar diagnóstico de motor Nissan", descripcion="Revisión de escáner en Taller Central", prioridad="Media", estado="En revisión", fecha_limite=ahora + timedelta(days=3)),
                models.Tarea(tenant_id=tenant_id, titulo="Confirmación telefónica agendamientos", descripcion="Llamadas de confirmación a clientes del día", prioridad="Baja", estado="Completada", fecha_limite=ahora - timedelta(days=1)),
            ]
            for t in tareas_demo:
                db.add(t)
            db.commit()
            print("Tareas Kanban demo creadas con exito.")

        print("Datos Demo de Noren preparados exitosamente!")
        print(f"Email Demo: {email_demo} / Pass: demo123")
    except Exception as e:
        print(f"Error sembrando demo: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed_demo()
