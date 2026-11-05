"""Pruebas del motor de horarios configurables por negocio."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, timedelta

_DB_FILE = os.path.join(tempfile.mkdtemp(), "horarios_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_DB_FILE}")
os.environ.setdefault("JWT_SECRET_KEY", "local-horarios-test-secret-long-enough-12")

import holidays
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core import models
from app.core.database import Base, SessionLocal, engine
from app.domain_agenda import horarios, router_cliente


def config(horario=None, duracion=60, **reglas):
    r = dict(reglas)
    if horario is not None:
        r["horario_semanal"] = horario
    return {"negocio": {"duracion_minutos": duracion}, "reglas_negocio": r}


def proximo(dia_semana: int) -> date:
    feriados = holidays.country_holidays("CL")
    dia = date.today() + timedelta(days=7)
    while dia.weekday() != dia_semana or dia in feriados:
        dia += timedelta(days=1)
    return dia


class MotorHorariosTest(unittest.TestCase):
    def test_tramos_por_dia_y_dias_cerrados(self):
        c = config({"0": [["09:00", "13:00"], ["14:00", "16:00"]], "5": [["10:00", "12:00"]]})
        self.assertEqual(horarios.inicios_del_dia(c, 0), ["09:00", "10:00", "11:00", "12:00", "14:00", "15:00"])
        self.assertEqual(horarios.inicios_del_dia(c, 5), ["10:00", "11:00"])
        self.assertEqual(horarios.inicios_del_dia(c, 6), [])
        self.assertEqual(horarios.dias_abiertos(c), {0, 5})

    def test_intervalo_distinto_a_la_duracion(self):
        c = config({"2": [["09:00", "11:00"]]}, duracion=60, intervalo_minutos=30)
        self.assertEqual(horarios.inicios_del_dia(c, 2), ["09:00", "09:30", "10:00"])

    def test_atencion_que_no_cabe_no_se_ofrece(self):
        c = config({"1": [["09:00", "10:30"]]}, duracion=60)
        self.assertEqual(horarios.inicios_del_dia(c, 1), ["09:00"])

    def test_tramos_se_ordenan_y_unen(self):
        self.assertEqual(
            horarios.normalizar_tramos([["14:00", "16:00"], ["09:00", "12:00"], ["11:00", "13:00"], ["18:00", "17:00"]]),
            [(540, 780), (840, 960)],
        )

    def test_legacy_inicios_fijos_se_respetan(self):
        c = {"negocio": {"duracion_minutos": 120}, "reglas_negocio": {
            "dias_habiles": [0], "bloques_horarios": {"0": ["09:00", "13:00", "15:30"]}}}
        self.assertEqual(horarios.inicios_del_dia(c, 0), ["09:00", "13:00", "15:30"])

    def test_legacy_rango_con_pausa(self):
        c = {"negocio": {"duracion_minutos": 60}, "reglas_negocio": {
            "dias_habiles": [3], "bloques_horarios": {"3": ["09:00", "18:00"]}, "pausa": ["13:00", "14:00"]}}
        self.assertEqual(horarios.horario_semanal_texto(c)["3"], [["09:00", "13:00"], ["14:00", "18:00"]])

    def test_cabe_en_horario(self):
        c = config({"0": [["09:00", "13:00"], ["14:00", "18:00"]]})
        lunes = proximo(0)
        self.assertTrue(horarios.cabe_en_horario(c, datetime.combine(lunes, datetime.min.time()).replace(hour=12), datetime.combine(lunes, datetime.min.time()).replace(hour=13)))
        self.assertFalse(horarios.cabe_en_horario(c, datetime.combine(lunes, datetime.min.time()).replace(hour=12, minute=30), datetime.combine(lunes, datetime.min.time()).replace(hour=13, minute=30)))

    def test_feriados_configurables(self):
        dieciocho = date(date.today().year + 1, 9, 18)
        self.assertTrue(horarios.cerrado_por_feriado(config({}), dieciocho))
        self.assertFalse(horarios.cerrado_por_feriado(config({}, atiende_feriados=True), dieciocho))


class AgendaConHorarioSemanalTest(unittest.TestCase):
    """Dos negocios distintos ven horarios distintos en su agenda pública."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        app = FastAPI()
        app.include_router(router_cliente.router, prefix="/cliente")
        cls.client = TestClient(app)

    def setUp(self):
        db = SessionLocal()
        for tenant_id in ("peluqueria", "taller-sab"):
            db.query(models.Tenant).filter(models.Tenant.id == tenant_id).delete()
        db.add(models.Tenant(id="peluqueria", nombre_empresa="Peluquería", config_json=json.dumps(
            config({"1": [["10:00", "13:00"], ["15:00", "17:00"]]}, duracion=30, intervalo_minutos=30)
            | {"negocio": {"duracion_minutos": 30, "equipos": ["Silla 1"]}})))
        db.add(models.Tenant(id="taller-sab", nombre_empresa="Taller", config_json=json.dumps(
            config({"5": [["08:00", "12:00"]]}, duracion=120) | {"negocio": {"duracion_minutos": 120, "equipos": ["A"]}})))
        db.commit()
        db.close()

    def _horas(self, tenant_id, fecha):
        return self.client.get("/cliente/api/horas-disponibles",
                               params={"fecha": fecha.isoformat(), "tenant_id": tenant_id}).json()["horas"]

    def test_cada_negocio_tiene_su_horario(self):
        martes, sabado = proximo(1), proximo(5)
        self.assertEqual(self._horas("peluqueria", martes),
                         ["10:00", "10:30", "11:00", "11:30", "12:00", "12:30", "15:00", "15:30", "16:00", "16:30"])
        self.assertEqual(self._horas("peluqueria", sabado), [])
        self.assertEqual(self._horas("taller-sab", sabado), ["08:00", "10:00"])
        self.assertEqual(self._horas("taller-sab", martes), [])

    def test_calendario_solo_habilita_dias_abiertos(self):
        r = self.client.get("/cliente/taller-sab/agendar_web")
        self.assertIn("const diasPermitidos = [5];", r.text)


if __name__ == "__main__":
    unittest.main()
