import os
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
engine = create_engine(os.getenv('DATABASE_URL').replace("postgres://", "postgresql://"))

with engine.begin() as conn:
    conn.execute(text('DROP TABLE IF EXISTS tareas CASCADE;'))
    conn.execute(text('DROP TABLE IF EXISTS usuarios CASCADE;'))

print("Tablas eliminadas.")
