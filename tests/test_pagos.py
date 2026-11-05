"""Pruebas de regresión de suscripciones (Mercado Pago y Stripe)."""
import hashlib
import hmac
import os
import tempfile
import unittest
from unittest.mock import patch

_DB_FILE = os.path.join(tempfile.mkdtemp(), "pagos_test.db")
os.environ.setdefault("DATABASE_URL", f"sqlite+pysqlite:///{_DB_FILE}")
os.environ.setdefault("JWT_SECRET_KEY", "local-pagos-test-secret-long-enough-1234")
os.environ["MERCADOPAGO_WEBHOOK_SECRET"] = "mp-test-secret"

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers import suscripcion
from app.core import mercadopago_utils, models
from app.core.database import Base, SessionLocal, engine

TENANT = "pagos-demo"


def firma_mp(data_id: str, request_id: str = "req-1", ts: str = "1700000000") -> dict:
    manifest = f"id:{data_id.lower()};request-id:{request_id};ts:{ts};"
    v1 = hmac.new(b"mp-test-secret", manifest.encode(), hashlib.sha256).hexdigest()
    return {"x-signature": f"ts={ts},v1={v1}", "x-request-id": request_id}


class PagosTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        app = FastAPI()
        app.include_router(suscripcion.router, prefix="/api/v1/suscripcion")
        cls.client = TestClient(app)

    def setUp(self):
        db = SessionLocal()
        db.query(models.Tenant).filter(models.Tenant.id == TENANT).delete()
        db.add(models.Tenant(id=TENANT, nombre_empresa="Pagos Demo", estado_suscripcion="prueba"))
        db.commit()
        db.close()
        for nombre in ("enviar_suscripcion_activada", "enviar_aviso_nueva_suscripcion"):
            patcher = patch.object(suscripcion, nombre)
            patcher.start()
            self.addCleanup(patcher.stop)

    def _tenant(self):
        db = SessionLocal()
        tenant = db.get(models.Tenant, TENANT)
        db.close()
        return tenant

    def _set(self, **campos):
        db = SessionLocal()
        tenant = db.get(models.Tenant, TENANT)
        for campo, valor in campos.items():
            setattr(tenant, campo, valor)
        db.commit()
        db.close()

    def _mp(self, preapproval_id: str, status: str):
        with patch.object(mercadopago_utils, "obtener_suscripcion",
                          return_value={"external_reference": TENANT, "status": status}):
            return self.client.post(
                f"/api/v1/suscripcion/mercadopago/webhook?data.id={preapproval_id}&type=subscription_preapproval",
                json={"type": "subscription_preapproval", "data": {"id": preapproval_id}},
                headers=firma_mp(preapproval_id),
            )

    # --- Mercado Pago -------------------------------------------------
    def test_mp_autorizada_activa_la_cuenta(self):
        self.assertEqual(self._mp("abc123", "authorized").json()["status"], "success")
        tenant = self._tenant()
        self.assertEqual(tenant.estado_suscripcion, "activa")
        self.assertEqual(tenant.mercado_pago_preapproval_id, "abc123")

    def test_mp_intento_viejo_cancelado_no_afecta_suscripcion_vigente(self):
        self._mp("vigente1", "authorized")
        r = self._mp("viejo99", "cancelled")
        self.assertEqual(r.json()["status"], "ignored")
        self.assertEqual(self._tenant().estado_suscripcion, "activa")

    def test_mp_cancelacion_de_la_vigente_deja_impaga_no_bloqueada(self):
        self._mp("vigente1", "authorized")
        self._mp("vigente1", "paused")
        self.assertEqual(self._tenant().estado_suscripcion, "impaga")

    def test_mp_pendiente_no_cambia_nada(self):
        self.assertEqual(self._mp("nuevo1", "pending").json()["status"], "pending")
        tenant = self._tenant()
        self.assertEqual(tenant.estado_suscripcion, "prueba")
        self.assertIsNone(tenant.mercado_pago_preapproval_id)

    def test_mp_firma_invalida_rechazada(self):
        r = self.client.post("/api/v1/suscripcion/mercadopago/webhook?data.id=abc",
                             json={"type": "subscription_preapproval"},
                             headers={"x-signature": "ts=1,v1=malo", "x-request-id": "r"})
        self.assertEqual(r.status_code, 401)

    def test_mp_cuerpo_vacio_no_rompe(self):
        r = self.client.post("/api/v1/suscripcion/mercadopago/webhook?data.id=abc",
                             content=b"", headers=firma_mp("abc"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ignored")

    def test_mp_firma_con_id_en_mayusculas(self):
        self.assertTrue(mercadopago_utils.firma_webhook_valida(
            signature=firma_mp("ABC123")["x-signature"], request_id="req-1", data_id="ABC123"))

    # --- Stripe -------------------------------------------------------
    def _stripe(self, tipo: str, objeto: dict):
        suscripcion._procesar_evento_stripe({"type": tipo, "data": {"object": objeto}}, SessionLocal())

    def test_stripe_pago_fallido_y_recuperado(self):
        self._stripe("checkout.session.completed",
                     {"client_reference_id": TENANT, "customer": "cus_1", "subscription": "sub_1"})
        self.assertEqual(self._tenant().estado_suscripcion, "activa")
        self._stripe("invoice.payment_failed", {"subscription": "sub_1"})
        self.assertEqual(self._tenant().estado_suscripcion, "impaga")
        self._stripe("invoice.paid", {"subscription": "sub_1"})
        self.assertEqual(self._tenant().estado_suscripcion, "activa")

    def test_stripe_eliminada_deja_impaga(self):
        self._set(stripe_subscription_id="sub_2", estado_suscripcion="activa")
        self._stripe("customer.subscription.deleted", {"id": "sub_2"})
        self.assertEqual(self._tenant().estado_suscripcion, "impaga")

    def test_stripe_suscripcion_ajena_ignorada(self):
        self._set(stripe_subscription_id="sub_3", estado_suscripcion="activa")
        self._stripe("customer.subscription.updated", {"id": "sub_otra", "status": "unpaid"})
        self.assertEqual(self._tenant().estado_suscripcion, "activa")

    def test_cuenta_desactivada_manual_no_se_reactiva_sola(self):
        self._set(stripe_subscription_id="sub_4", estado_suscripcion="cancelada")
        self._stripe("invoice.paid", {"subscription": "sub_4"})
        self.assertEqual(self._tenant().estado_suscripcion, "cancelada")


class CuentaImpagaTest(unittest.TestCase):
    """Una cuenta impaga puede entrar, pero el panel la lleva a pagar."""

    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)

    def test_middleware_redirige_a_suscripcion(self):
        from app import main
        from app.core import security

        db = SessionLocal()
        db.query(models.Tenant).filter(models.Tenant.id == "impaga-demo").delete()
        db.add(models.Tenant(id="impaga-demo", nombre_empresa="Impaga", estado_suscripcion="impaga"))
        db.commit()
        db.close()
        token = security.create_access_token(1, "admin", "impaga-demo", "a@b.cl")
        # Sin `with`: no se ejecutan los eventos de arranque (scheduler).
        client = TestClient(main.app)
        client.cookies.set("access_token", f"Bearer {token}")
        r = client.get("/admin/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], "/admin/suscripcion")


if __name__ == "__main__":
    unittest.main()
