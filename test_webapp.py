import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from database import init_db, save_affiliate, set_affiliate_active
from webapp import app


class WebAppTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["DB_PATH"] = str(Path(self.temp_dir.name) / "test.db")
        os.environ["BRAND_NAME"] = "Baltigo & Teste"
        os.environ["ALLOWED_CHECKOUT_HOSTS"] = "pay.cakto.com.br"
        os.environ["CHECKOUT_MONTHLY"] = "MENSAL123"
        os.environ["CHECKOUT_QUARTERLY"] = "TRI123"
        os.environ["CHECKOUT_SEMIANNUAL"] = "SEM123"
        os.environ["CHECKOUT_ANNUAL"] = "ANUAL123"
        init_db()
        save_affiliate(
            123,
            "usuario",
            "apelido-publico",
            "pagina-teste",
            "affiliate-123",
            {plan: "affiliate" for plan in ("monthly", "quarterly", "semiannual", "annual")},
            {
                "monthly": "MENSAL123",
                "quarterly": "TRI123",
                "semiannual": "SEM123",
                "annual": "ANUAL123",
            },
            active=False,
        )
        self.client = TestClient(app)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_health(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_pending_page_is_not_public(self):
        self.assertEqual(self.client.get("/pagina-teste").status_code, 404)

    def test_approved_page_is_public_and_safe(self):
        set_affiliate_active(123, True)
        response = self.client.get("/pagina-teste")
        self.assertEqual(response.status_code, 200)
        self.assertIn("apelido-publico", response.text)
        self.assertNotIn("usuario", response.text)
        self.assertIn("affiliate-123", response.text)
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")


if __name__ == "__main__":
    unittest.main()
