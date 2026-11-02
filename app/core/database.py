import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from pathlib import Path
from sqlalchemy.engine import Engine
from dotenv import load_dotenv

load_dotenv() # Load variables from .env

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # Ajustamos path ya que ahora estamos en app/core/
DB_PATH = BASE_DIR / "agendamientos.db"

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")
if not SQLALCHEMY_DATABASE_URL:
    raise RuntimeError("DATABASE_URL debe estar configurada")

# Fix postgres:// to postgresql:// if needed for SQLAlchemy
if SQLALCHEMY_DATABASE_URL.startswith("postgres://"):
    SQLALCHEMY_DATABASE_URL = SQLALCHEMY_DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Specific args for SQLite
connect_args = {}
pool_options = {}
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False, "timeout": 15}
elif os.getenv("VERCEL") == "1":
    # Limita conexiones por instancia: el pool predeterminado de SQLAlchemy
    # puede multiplicar conexiones al escalar funciones serverless.
    pool_options = {
        "pool_size": int(os.getenv("DB_POOL_SIZE", "1")),
        "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "0")),
        "pool_timeout": int(os.getenv("DB_POOL_TIMEOUT", "10")),
    }

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args=connect_args,
    pool_pre_ping=True,
    pool_recycle=300,
    **pool_options,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
