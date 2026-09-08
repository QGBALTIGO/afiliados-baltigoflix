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
        os.environ["OFFICIAL_SITE_URL"] = "https://baltigoflix.com.br"
        os.environ["OFFICIAL_SITE_INTEGRATION_ENABLED"] = "false"
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
        self.assertEqual(self.client.get("/api/affiliate/pagina-teste").status_code, 404)

    def test_approved_page_uses_safe_fallback_until_integration_is_enabled(self):
        set_affiliate_active(123, True)
        response = self.client.get("/pagina-teste")
        self.assertEqual(response.status_code, 200)
        self.assertIn("affiliate-123", response.text)

    def test_approved_page_redirects_after_integration_is_enabled(self):
        set_affiliate_active(123, True)
        os.environ["OFFICIAL_SITE_INTEGRATION_ENABLED"] = "true"
        try:
            response = self.client.get("/pagina-teste", follow_redirects=False)
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response.headers["location"],
                "https://baltigoflix.com.br/?afiliado=pagina-teste",
            )
        finally:
            os.environ["OFFICIAL_SITE_INTEGRATION_ENABLED"] = "false"

    def test_approved_affiliate_api_returns_safe_checkouts(self):
        set_affiliate_active(123, True)
        response = self.client.get(
            "/api/affiliate/pagina-teste",
            headers={"Origin": "https://baltigoflix.com.br"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("usuario", response.text)
        self.assertEqual(response.json()["slug"], "pagina-teste")
        self.assertEqual(
            response.json()["checkouts"]["monthly"],
            "https://pay.cakto.com.br/MENSAL123?affiliate=affiliate-123",
        )
        self.assertEqual(
            response.headers["access-control-allow-origin"],
            "https://baltigoflix.com.br",
        )
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("Content-Security-Policy", response.headers)
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")


if __name__ == "__main__":
    unittest.main()
