"""Pruebas de regresión del flujo público de agendamiento (/cliente/{tenant}/agendar_web)."""
import json
import os
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from urllib.parse import unquote
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

    def _configurar(self, negocio=None, reglas=None):
        db = SessionLocal()
        tenant = db.get(models.Tenant, TENANT)
        config = json.loads(tenant.config_json)
        config["negocio"].update(negocio or {})
        config["reglas_negocio"].update(reglas or {})
        tenant.config_json = json.dumps(config)
        db.commit()
        db.close()

    def _horas(self):
        return self.client.get("/cliente/api/horas-disponibles",
                               params={"fecha": self.fecha.isoformat(), "tenant_id": TENANT}).json()["horas"]

    def test_pausa_divide_la_jornada(self):
        self._configurar(
            negocio={"duracion_minutos": 60},
            reglas={"bloques_horarios": {"0": ["09:00", "18:00"]}, "pausa": ["13:00", "14:30"]},
        )
        r = self.client.get(BOOKING_URL, params={"fecha": self.fecha.isoformat()})
        self.assertIn('value="12:00"', r.text)
        self.assertNotIn('value="13:00"', r.text)
        self.assertIn('value="14:30"', r.text)
        # Un horario dentro de la pausa no se puede reservar aunque se fuerce el POST.
        self.assertEqual(self._post(hora="13:00").status_code, 409)

    def test_duracion_en_minutos(self):
        self._configurar(negocio={"duracion_minutos": 30},
                         reglas={"bloques_horarios": {"0": ["09:00", "10:30"]}})
        r = self.client.get(BOOKING_URL, params={"fecha": self.fecha.isoformat()})
        for hora in ("09:00", "09:30", "10:00"):
            self.assertIn(f'value="{hora}"', r.text)
        self.assertEqual(self._post(hora="09:30").status_code, 200)
        db = SessionLocal()
        cita = db.query(models.Agendamiento).one()
        self.assertEqual((cita.fecha_termino - cita.fecha_inicio).total_seconds(), 1800)
        db.close()

    def test_anticipacion_minima_oculta_horarios_cercanos(self):
        # La fecha de prueba está a ~7 días; exigir 30 días de anticipación la deja sin horarios.
        self._configurar(reglas={"horas_minimas_anticipacion": 720})
        self.assertEqual(self._horas(), [])
        self.assertEqual(self._post().status_code, 409)

    def test_fecha_minima_sin_dias_habiles_no_se_cuelga(self):
        db = SessionLocal()
        tenant = db.get(models.Tenant, TENANT)
        tenant.config_json = json.dumps({"reglas_negocio": {"dias_habiles": []}})
        db.commit()
        self.assertIsNotNone(router_cliente.obtener_fecha_minima_habil(db, TENANT))
        db.close()


class ConfiguracionNegocioTest(unittest.TestCase):
    """El dueño puede ajustar duración, equipos, pausa y anticipación desde el panel."""

    @classmethod
    def setUpClass(cls):
        from app.core.auth_deps import CurrentUser, verificar_login
        from app.domain_crm import router_admin

        Base.metadata.create_all(bind=engine)
        app = FastAPI()
        app.include_router(router_admin.router, prefix="/admin")
        app.dependency_overrides[verificar_login] = lambda: CurrentUser(1, "admin@demo.cl", "cfg-demo", "admin")
        cls.client = TestClient(app)

    def setUp(self):
        db = SessionLocal()
        db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == "cfg-demo").delete()
        db.query(models.Tenant).filter(models.Tenant.id == "cfg-demo").delete()
        db.add(models.Tenant(id="cfg-demo", nombre_empresa="Demo", config_json=json.dumps({
            "reglas_negocio": {"regla_propia": True},
        })))
        db.commit()
        db.close()

    def _config(self):
        db = SessionLocal()
        config = json.loads(db.get(models.Tenant, "cfg-demo").config_json)
        db.close()
        return config

    def test_guarda_horario_por_dia(self):
        r = self.client.post("/admin/configuracion-negocio", data={
            "nombre_empresa": "Demo", "duracion_minutos": "45", "equipos": "Box 1, Box 2",
            "dia_0_abierto": "1", "tramo_0_inicio": ["09:00", "14:00"], "tramo_0_fin": ["13:00", "18:00"],
            "dia_5_abierto": "1", "tramo_5_inicio": "10:00", "tramo_5_fin": "14:00",
            # Domingo desmarcado: aunque traiga horas, queda cerrado.
            "tramo_6_inicio": "09:00", "tramo_6_fin": "12:00",
            "intervalo_minutos": "30", "atiende_feriados": "1", "horas_minimas_anticipacion": "24",
        }, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertIn("guardado=1", r.headers["location"])
        config = self._config()
        reglas = config["reglas_negocio"]
        self.assertEqual(config["negocio"]["duracion_minutos"], 45)
        self.assertEqual(config["negocio"]["equipos"], ["Box 1", "Box 2"])
        self.assertEqual(reglas["horario_semanal"]["0"], [["09:00", "13:00"], ["14:00", "18:00"]])
        self.assertEqual(reglas["horario_semanal"]["5"], [["10:00", "14:00"]])
        self.assertEqual(reglas["horario_semanal"]["6"], [])
        self.assertEqual(reglas["dias_habiles"], [0, 5])
        self.assertEqual(reglas["intervalo_minutos"], 30)
        self.assertTrue(reglas["atiende_feriados"])
        self.assertEqual(reglas["horas_minimas_anticipacion"], 24)
        self.assertNotIn("bloques_horarios", reglas)
        self.assertTrue(reglas["regla_propia"], "no debe borrar otras reglas")

        pagina = self.client.get("/admin/configuracion-negocio")
        self.assertEqual(pagina.status_code, 200)
        self.assertIn('value="Box 1, Box 2"', pagina.text)
        self.assertIn('name="tramo_0_inicio" value="14:00"', pagina.text)
        self.assertIn('name="tramo_5_fin" value="14:00"', pagina.text)
        self.assertIn('name="dia_6_abierto" value="1" class="h-4 w-4 accent-blue-700" data-toggle-dia >', pagina.text)

    def test_tramo_invalido_no_se_guarda(self):
        r = self.client.post("/admin/configuracion-negocio", data={
            "nombre_empresa": "Demo", "dia_1_abierto": "1", "tramo_1_inicio": "18:00", "tramo_1_fin": "09:00",
        }, follow_redirects=False)
        self.assertIn("error=", r.headers["location"])
        self.assertIn("Martes", unquote(r.headers["location"]))
        self.assertNotIn("negocio", self._config())

    def test_sin_dias_abiertos_no_se_guarda(self):
        r = self.client.post("/admin/configuracion-negocio", data={"nombre_empresa": "Demo"}, follow_redirects=False)
        self.assertIn("al menos un d", unquote(r.headers["location"]))

    def test_reprogramar_respeta_horario_del_negocio(self):
        from app.domain_crm.router_admin import verificar_disponibilidad_detalle
        self.client.post("/admin/configuracion-negocio", data={
            "nombre_empresa": "Demo", "duracion_minutos": "60",
            "dia_0_abierto": "1", "tramo_0_inicio": ["09:00", "15:00"], "tramo_0_fin": ["13:00", "19:00"],
        })
        lunes = proximo_lunes_habil()
        db = SessionLocal()
        ok, _ = verificar_disponibilidad_detalle(db, "domicilio_taller", datetime.combine(lunes, time(17, 30)), 1, tenant_id="cfg-demo")
        self.assertTrue(ok)
        ok, msg = verificar_disponibilidad_detalle(db, "domicilio_taller", datetime.combine(lunes, time(12, 30)), 1, tenant_id="cfg-demo")
        self.assertFalse(ok)
        self.assertIn("09:00–13:00, 15:00–19:00", msg)
        ok, msg = verificar_disponibilidad_detalle(db, "domicilio_taller", datetime.combine(lunes + timedelta(days=1), time(10, 0)), 1, tenant_id="cfg-demo")
        self.assertFalse(ok)
        self.assertIn("cerrada los martes", msg)
        db.close()

    def test_onboarding_nuevo_negocio(self):
        db = SessionLocal()
        tenant = db.get(models.Tenant, "cfg-demo")
        tenant.config_json = json.dumps({"configuracion_inicial_completa": False})
        db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == "cfg-demo").delete()
        db.commit()
        db.close()
        # El usuario desmarca el correo: igual se crea, porque la reserva lo necesita.
        r = self.client.post("/admin/configuracion-inicial", data={
            "nombre_empresa": "Demo", "giro": "Estética", "servicio_principal": "Limpieza facial",
            "duracion_minutos": "90", "hora_inicio": "10:00", "hora_fin": "19:00",
            "dias_habiles": ["1", "2", "3"], "campos_cliente": ["nombre"],
        }, follow_redirects=False)
        self.assertEqual(r.headers["location"], "/admin/onboarding")
        db = SessionLocal()
        campos = {c.nombre_tecnico for c in db.query(models.CampoFormulario).filter(models.CampoFormulario.tenant_id == "cfg-demo")}
        db.close()
        self.assertEqual(campos, {"nombre", "correo"})
        self.assertEqual(self._config()["reglas_negocio"]["horario_semanal"]["1"], [["10:00", "19:00"]])

        guia = self.client.get("/admin/onboarding")
        self.assertEqual(guia.status_code, 200)
        self.assertIn("Primeros pasos", guia.text)
        self.assertIn("10:00–19:00", guia.text)
        self.assertIn("Cerrado", guia.text)
        self.assertIn("/admin/configuracion-negocio#horarios", guia.text)

        # Desde la guía se puede abrir la configuración y volver.
        pagina = self.client.get("/admin/configuracion-negocio", follow_redirects=False)
        self.assertEqual(pagina.status_code, 200)
        self.assertIn("Volver a la guía", pagina.text)

    def test_links_agenda_son_del_negocio(self):
        links = self.client.get("/admin/links-agenda").json()
        self.assertIn("/cliente/cfg-demo/agendar_web", links["local"]["url"])
        self.assertNotIn("domicilio", links)
        r = self.client.get("/admin/agendar-emergencia-total", follow_redirects=False)
        self.assertTrue(r.headers["location"].startswith("/cliente/cfg-demo/agendar_web"))


if __name__ == "__main__":
    unittest.main()
