"""Pruebas de regresión del flujo público de agendamiento (/cliente/{tenant}/agendar_web)."""
import json
import os
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

_DB_FILE = os.path.join(tempfile.mkdtemp(), "agenda_test.db")
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_DB_FILE}"
os.environ.setdefault("JWT_SECRET_KEY", "local-agenda-test-secret-long-enough-123")

import holidays
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import models
from app.core.database import Base, SessionLocal, engine
from app.domain_agenda import router_cliente

TENANT = "taller-demo"
BOOKING_URL = f"/cliente/{TENANT}/agendar_web"


def proximo_lunes_habil() -> date:
    feriados = holidays.country_holidays("CL")
    dia = date.today() + timedelta(days=7)
    while dia.weekday() != 0 or dia in feriados:
        dia += timedelta(days=1)
    return dia


class AgendaPublicaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        app = FastAPI()
        app.include_router(router_cliente.router, prefix="/cliente")
        cls.client = TestClient(app)
        cls.fecha = proximo_lunes_habil()

    def setUp(self):
        db = SessionLocal()
        for model in (models.TimelineEvent, models.Agendamiento, models.Cliente,
                      models.CampoFormulario, models.DiaBloqueado, models.Tenant):
            db.query(model).delete()
        db.add(models.Tenant(
            id=TENANT,
            nombre_empresa="Taller Demo",
            config_json=json.dumps({
                "negocio": {"duracion_minutos": 120, "equipos": ["Equipo A"], "servicio_principal": "revisión"},
                "reglas_negocio": {
                    "dias_habiles": [0, 1, 2, 3, 4],
                    "bloques_horarios": {"0": ["09:00", "13:00", "15:30"]},
                },
            }),
        ))
        db.flush()
        for orden, (tecnico, tipo) in enumerate([("nombre", "text"), ("correo", "email"), ("rut", "text")]):
            db.add(models.CampoFormulario(
                tenant_id=TENANT, label=tecnico.title(), tipo_campo=tipo, orden=orden,
                activo=True, subtipo_servicio="taller", nombre_tecnico=tecnico,
            ))
        db.commit()
        self.campos = {c.nombre_tecnico: c.id for c in db.query(models.CampoFormulario).all()}
        db.close()
        patcher = patch.object(router_cliente, "enviar_notificacion")
        self.notificacion = patcher.start()
        self.addCleanup(patcher.stop)

    def _post(self, hora="09:00", rut="11111111-1", **extra):
        data = {
            "tipo_servicio": "domicilio_taller", "subtipo": "local",
            "fecha": self.fecha.isoformat(), "hora": hora, "duracion_horas": "2",
            f"dinamico_{self.campos['nombre']}": "Ana",
            f"dinamico_{self.campos['correo']}": "ana@example.com",
            f"dinamico_{self.campos['rut']}": rut,
        }
        data.update(extra)
        return self.client.post(BOOKING_URL, data=data)

    def test_muestra_horas_disponibles(self):
        r = self.client.get(BOOKING_URL, params={"fecha": self.fecha.isoformat()})
        self.assertEqual(r.status_code, 200)
        for hora in ("09:00", "13:00", "15:30"):
            self.assertIn(f'value="{hora}"', r.text)

    def test_dia_sin_horas_muestra_mensaje_y_vuelve_al_calendario(self):
        domingo = self.fecha + timedelta(days=6)
        r = self.client.get(BOOKING_URL, params={"fecha": domingo.isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertIn("No quedan horarios disponibles", r.text)
        self.assertIn('id="fecha"', r.text)

    def test_reserva_exitosa_usa_duracion_del_negocio(self):
        r = self._post(duracion_horas="8")
        self.assertEqual(r.status_code, 200, r.text[:500])
        self.assertIn("Solicitud recibida", r.text)
        self.assertIn("ana@example.com", r.text)
        db = SessionLocal()
        cita = db.query(models.Agendamiento).one()
        self.assertEqual(cita.duracion_horas, 2)
        self.assertEqual(cita.equipo, "Equipo A")
        db.close()
        self.notificacion.assert_called_once()

    def test_horario_ocupado_responde_mensaje_y_no_500(self):
        self.assertEqual(self._post().status_code, 200)
        r = self._post(rut="22222222-2")
        self.assertEqual(r.status_code, 409)
        self.assertIn("ya no está disponible", r.text)
        db = SessionLocal()
        self.assertEqual(db.query(models.Agendamiento).count(), 1)
        db.close()

    def test_dia_bloqueado_responde_mensaje(self):
        db = SessionLocal()
        db.add(models.DiaBloqueado(tenant_id=TENANT, fecha=self.fecha))
        db.commit()
        db.close()
        r = self._post()
        self.assertEqual(r.status_code, 409)
        self.assertIn("se encuentra cerrado", r.text)

    def test_fecha_invalida_responde_mensaje(self):
        r = self._post(hora="")
        self.assertEqual(r.status_code, 422)
        self.assertIn("fecha y hora válidas", r.text)

    def test_api_horas_respeta_tenant(self):
        r = self.client.get("/cliente/api/horas-disponibles",
                            params={"fecha": self.fecha.isoformat(), "tenant_id": TENANT})
        self.assertEqual(r.json(), {"horas": ["09:00", "13:00", "15:30"]})

    def test_fecha_minima_sin_dias_habiles_no_se_cuelga(self):
        db = SessionLocal()
        tenant = db.get(models.Tenant, TENANT)
        tenant.config_json = json.dumps({"reglas_negocio": {"dias_habiles": []}})
        db.commit()
        self.assertIsNotNone(router_cliente.obtener_fecha_minima_habil(db, TENANT))
        db.close()


if __name__ == "__main__":
    unittest.main()
