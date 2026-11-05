# Norem

Plataforma multi-tenant de agenda, clientes, tareas y reservas. La aplicación usa FastAPI, SQLAlchemy y PostgreSQL; el despliegue productivo corre en Vercel.

## Desarrollo local

1. Usa Python 3.10 o superior y crea un entorno virtual.
2. Instala las dependencias: `pip install -r requirements.txt`.
3. Configura las variables de entorno según `.env.example` (no subas secretos al repositorio).
4. Inicia la aplicación: `uvicorn app.main:app --reload --port 8000`.

La API pública de agenda está documentada en [`docs/PUBLIC_API.md`](docs/PUBLIC_API.md). Los recordatorios y avisos se envían por correo electrónico; no hay integración de mensajería externa activa.

## Seguridad

- Configura `DATABASE_URL`, `JWT_SECRET_KEY` y `CRON_SECRET` mediante el gestor de secretos del entorno.
- Usa secretos aleatorios fuertes y distintos por ambiente; nunca uses valores de ejemplo en producción.
- Revisa [`scripts/enable_rls.sql`](scripts/enable_rls.sql) como auditoría de solo lectura. No activa RLS.
- Ejecuta las pruebas locales con `python -m unittest discover -s tests -v`.
