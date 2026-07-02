import sqlite3
import os
import pytz
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# 1. Asegurar que estamos en el contexto correcto
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.append(str(BASE_DIR))

from app.core import models

load_dotenv()
PG_URL = os.getenv("DATABASE_URL")
if PG_URL and PG_URL.startswith("postgres://"):
    PG_URL = PG_URL.replace("postgres://", "postgresql://", 1)

# Crear engine para PG
pg_engine = create_engine(PG_URL)
SessionLocalPG = sessionmaker(autocommit=False, autoflush=False, bind=pg_engine)

def migrar_datos():
    db_path = BASE_DIR / "agendamientos.db"
    
    if "YOUR-PASSWORD" in PG_URL:
        print("❌ ERROR: Debes cambiar [YOUR-PASSWORD] por tu contraseña real en el archivo .env")
        return
        
    print(f"📦 Conectando a SQLite local: {db_path}")
    sqlite_conn = sqlite3.connect(db_path)
    sqlite_conn.row_factory = sqlite3.Row
    cursor = sqlite_conn.cursor()

    print(f"🚀 Conectando a PostgreSQL en Supabase...")
    pg_db = SessionLocalPG()
    
    try:
        # Migrar Tenants (si no existe el default)
        tenant_default = pg_db.query(models.Tenant).filter(models.Tenant.id == "default").first()
        if not tenant_default:
            tenant_default = models.Tenant(id="default", nombre_empresa="Nexora Principal")
            pg_db.add(tenant_default)
            pg_db.commit()

        # 1. Campos Formulario
        cursor.execute("SELECT * FROM campos_formulario")
        campos = cursor.fetchall()
        for c in campos:
            # Comprobar si existe
            existe = pg_db.query(models.CampoFormulario).filter(models.CampoFormulario.id == c['id']).first()
            if not existe:
                nuevo_campo = models.CampoFormulario(
                    id=c['id'],
                    tenant_id="default",
                    label=c['label'],
                    tipo_campo=c['tipo_campo'],
                    opciones=c['opciones'],
                    orden=c['orden'],
                    activo=bool(c['activo']),
                    obligatorio=bool(c['obligatorio']),
                    tipo_servicio=c['tipo_servicio'],
                    subtipo_servicio=c['subtipo_servicio'],
                    es_sistema=bool(c['es_sistema']),
                    nombre_tecnico=c['nombre_tecnico']
                )
                pg_db.add(nuevo_campo)
        pg_db.commit()
        print(f"✅ Migrados {len(campos)} Campos Dinámicos")

        # 2. Días Bloqueados
        cursor.execute("SELECT * FROM dias_bloqueados")
        dias = cursor.fetchall()
        for d in dias:
            fecha_obj = datetime.strptime(d['fecha'], "%Y-%m-%d").date()
            existe = pg_db.query(models.DiaBloqueado).filter(models.DiaBloqueado.fecha == fecha_obj).first()
            if not existe:
                nuevo_dia = models.DiaBloqueado(
                    tenant_id="default",
                    fecha=fecha_obj,
                    motivo=d['motivo']
                )
                pg_db.add(nuevo_dia)
        pg_db.commit()
        print(f"✅ Migrados {len(dias)} Días Bloqueados")

        # 3. Agendamientos
        cursor.execute("SELECT * FROM agendamientos")
        agendamientos = cursor.fetchall()
        
        tz_chile = pytz.timezone("America/Santiago")
        
        for a in agendamientos:
            existe = pg_db.query(models.Agendamiento).filter(models.Agendamiento.id == a['id']).first()
            if not existe:
                # Convertir fechas de string SQLite a datetime para Postgres
                fecha_inicio = datetime.strptime(a['fecha_inicio'], "%Y-%m-%d %H:%M:%S.%f") if "." in a['fecha_inicio'] else datetime.strptime(a['fecha_inicio'], "%Y-%m-%d %H:%M:%S")
                fecha_termino = datetime.strptime(a['fecha_termino'], "%Y-%m-%d %H:%M:%S.%f") if "." in a['fecha_termino'] else datetime.strptime(a['fecha_termino'], "%Y-%m-%d %H:%M:%S")
                creado_en = datetime.strptime(a['creado_en'], "%Y-%m-%d %H:%M:%S.%f") if "." in a['creado_en'] else datetime.strptime(a['creado_en'], "%Y-%m-%d %H:%M:%S")

                # Sanitizar enteros
                try:
                    km = int(str(a['kilometraje']).strip())
                except (ValueError, TypeError):
                    km = None
                    
                try:
                    duracion = int(str(a['duracion_horas']).strip())
                except (ValueError, TypeError):
                    duracion = 2

                nuevo_agendamiento = models.Agendamiento(
                    id=a['id'],
                    tenant_id="default",
                    rut=a['rut'],
                    tipo_servicio=a['tipo_servicio'],
                    nombre=a['nombre'],
                    apellido=a['apellido'],
                    telefono=a['telefono'],
                    correo=a['correo'],
                    direccion=a['direccion'],
                    tipo_vivienda=a['tipo_vivienda'],
                    marca=a['marca'],
                    modelo=a['modelo'],
                    patente=a['patente'],
                    kilometraje=km,
                    fecha_inicio=fecha_inicio,
                    fecha_termino=fecha_termino,
                    creado_en=creado_en,
                    duracion_horas=duracion,
                    equipo=a['equipo'],
                    subtipo=a['subtipo'],
                    utm_link=a['utm_link'],
                    utm_source_real=a['utm_source_real'],
                    nota_interna=a['nota_interna'],
                    boton_enviado=bool(a['boton_enviado']),
                    nota_compartida=a['nota_compartida'],
                    estado=a['estado'],
                )
                
                if a['fecha_cancelacion']:
                    nuevo_agendamiento.fecha_cancelacion = datetime.strptime(a['fecha_cancelacion'], "%Y-%m-%d %H:%M:%S.%f") if "." in a['fecha_cancelacion'] else datetime.strptime(a['fecha_cancelacion'], "%Y-%m-%d %H:%M:%S")

                pg_db.add(nuevo_agendamiento)
        pg_db.commit()
        print(f"✅ Migrados {len(agendamientos)} Agendamientos")
        
        # 4. Respuestas
        cursor.execute("SELECT * FROM respuestas_campos")
        respuestas = cursor.fetchall()
        for r in respuestas:
            existe = pg_db.query(models.RespuestaCampo).filter(models.RespuestaCampo.id == r['id']).first()
            if not existe:
                nueva_respuesta = models.RespuestaCampo(
                    id=r['id'],
                    tenant_id="default",
                    agendamiento_id=r['agendamiento_id'],
                    campo_id=r['campo_id'],
                    valor=r['valor']
                )
                pg_db.add(nueva_respuesta)
        pg_db.commit()
        print(f"✅ Migradas {len(respuestas)} Respuestas Dinámicas")
        
        # 5. UTM
        cursor.execute("SELECT * FROM utm_registros")
        utms = cursor.fetchall()
        for u in utms:
            existe = pg_db.query(models.UTMRegistro).filter(models.UTMRegistro.id == u['id']).first()
            if not existe:
                fecha_reg = datetime.strptime(u['fecha_registro'], "%Y-%m-%d %H:%M:%S.%f") if "." in u['fecha_registro'] else datetime.strptime(u['fecha_registro'], "%Y-%m-%d %H:%M:%S")
                nuevo_utm = models.UTMRegistro(
                    id=u['id'],
                    tenant_id="default",
                    agendamiento_id=u['agendamiento_id'],
                    utm_source=u['utm_source'],
                    utm_medium=u['utm_medium'],
                    utm_campaign=u['utm_campaign'],
                    fecha_registro=fecha_reg,
                    ip=u['ip'],
                    user_agent=u['user_agent']
                )
                pg_db.add(nuevo_utm)
        pg_db.commit()
        print(f"✅ Migrados {len(utms)} Registros UTM")
        
        # Resetear las secuencias de Postgres para las Primary Keys (Crucial tras insertar IDs manuales)
        try:
            tablas = ['campos_formulario', 'dias_bloqueados', 'agendamientos', 'respuestas_campos', 'utm_registros']
            for tabla in tablas:
                pg_db.execute(f"SELECT setval('{tabla}_id_seq', (SELECT MAX(id) FROM {tabla}));")
            pg_db.commit()
            print("✅ Secuencias de base de datos actualizadas")
        except Exception as e:
            print(f"⚠️ Aviso al resetear secuencias: {e}")
            pg_db.rollback()

        print("\n🎉 ¡Migración ETL Completada Exitosamente!")

    except Exception as e:
        pg_db.rollback()
        print(f"❌ Error durante la migración: {e}")
    finally:
        sqlite_conn.close()
        pg_db.close()

if __name__ == "__main__":
    migrar_datos()
