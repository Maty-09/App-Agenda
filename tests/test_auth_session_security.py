"""Regression tests for server-side session and role validation."""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///:memory:")
os.environ.setdefault("JWT_SECRET_KEY", "local-auth-security-test-secret-long-enough")

import jwt as pyjwt
from fastapi import HTTPException
from starlette.requests import Request

from app.api import deps as api_deps
from app.core import auth_deps, models, security
from app.infrastructure.email_utils import crear_token_confirmacion, validar_token_confirmacion


class FakeQuery:
    def __init__(self, model, user, tenant):
        self.model = model
        self.user = user
        self.tenant = tenant
        self.criteria = ()

    def filter(self, *criteria):
        self.criteria = criteria
        return self

    def first(self):
        row = self.user if self.model is models.Usuario else self.tenant
        if row is None:
            return None
        for criterion in self.criteria:
            key = criterion.left.key
            expected = True if key == "sesion_activa" else getattr(criterion.right, "value", None)
            if getattr(row, key, None) != expected:
                return None
        return row


class FakeSession:
    def __init__(self, user, tenant):
        self.user = user
        self.tenant = tenant

    def query(self, model):
        return FakeQuery(model, self.user, self.tenant)

    def close(self):
        pass


def make_request(token):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/admin/dashboard",
        "raw_path": b"/admin/dashboard",
        "query_string": b"",
        "headers": [(b"cookie", f"access_token=Bearer {token}".encode())],
        "server": ("norem.test", 443),
        "client": ("127.0.0.1", 12345),
    }
    return Request(scope)


class AuthSessionSecurityTests(unittest.TestCase):
    def setUp(self):
        self.user = type("User", (), {
            "id": 7,
            "tenant_id": "tenant-a",
            "sesion_activa": True,
            "rol": "operador",
            "email": "actual@example.test",
        })()
        self.tenant = type("Tenant", (), {"id": "tenant-a", "estado_suscripcion": "activa"})()

    def token(self, **claims):
        payload = {"sub": "7", "tenant_id": "tenant-a", "rol": "admin", **claims}
        return pyjwt.encode(payload, security.SECRET_KEY, algorithm=security.ALGORITHM)

    def test_admin_cookie_uses_current_database_role_not_stale_jwt_claim(self):
        fake_db = FakeSession(self.user, self.tenant)
        with patch.object(auth_deps, "SessionLocal", return_value=fake_db):
            current = auth_deps.verificar_login(make_request(self.token()))
        self.assertEqual(current.rol, "operador")
        self.assertEqual(current.email, "actual@example.test")

    def test_admin_cookie_is_rejected_after_session_revocation(self):
        self.user.sesion_activa = False
        fake_db = FakeSession(self.user, self.tenant)
        with patch.object(auth_deps, "SessionLocal", return_value=fake_db):
            with self.assertRaises(HTTPException) as error:
                auth_deps.verificar_login(make_request(self.token()))
        self.assertEqual(error.exception.status_code, 401)

    def test_api_bearer_is_rejected_after_session_revocation(self):
        self.user.sesion_activa = False
        fake_db = FakeSession(self.user, self.tenant)
        with self.assertRaises(HTTPException) as error:
            api_deps.get_current_user(make_request(""), fake_db, self.token())
        self.assertEqual(error.exception.status_code, 401)

    def test_api_bearer_is_rejected_for_deactivated_tenant(self):
        self.tenant.estado_suscripcion = "cancelada"
        fake_db = FakeSession(self.user, self.tenant)
        with self.assertRaises(HTTPException) as error:
            api_deps.get_current_user(make_request(""), fake_db, self.token())
        self.assertEqual(error.exception.status_code, 403)

    def test_booking_confirmation_token_is_signed_and_bound_to_tenant(self):
        booking = type("Booking", (), {"id": 12345, "tenant_id": "tenant-a"})()
        token = crear_token_confirmacion(booking)
        self.assertNotEqual(token, str(booking.id))
        self.assertEqual(validar_token_confirmacion(token), (12345, "tenant-a"))
        self.assertIsNone(validar_token_confirmacion(token[:-1] + ("A" if token[-1] != "A" else "B")))

if __name__ == "__main__":
    unittest.main()
