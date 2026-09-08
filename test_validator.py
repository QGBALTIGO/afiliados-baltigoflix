import os
import unittest

from validator import configuration_errors, validate_affiliate_link, validate_checkout_link


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        os.environ["ALLOWED_CHECKOUT_HOSTS"] = "pay.cakto.com.br"
        os.environ["CHECKOUT_MONTHLY"] = "MENSAL123"
        os.environ["CHECKOUT_QUARTERLY"] = "TRI123"
        os.environ["CHECKOUT_SEMIANNUAL"] = "SEM123"
        os.environ["CHECKOUT_ANNUAL"] = "ANUAL123"

    def test_configuration_is_valid(self):
        self.assertEqual(configuration_errors(), [])

    def test_valid(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123?affiliate=abc-123",
            "monthly",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.affiliate_id, "abc-123")

    def test_multiple_checkouts_for_same_plan(self):
        os.environ["CHECKOUT_QUARTERLY"] = "TRI123, TRI456"
        first = validate_checkout_link(
            "https://pay.cakto.com.br/TRI123?affiliate=abc", "quarterly"
        )
        second = validate_checkout_link(
            "https://pay.cakto.com.br/TRI456?affiliate=abc", "quarterly"
        )
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(second.checkout_id, "TRI456")

    def test_any_official_plan_is_accepted_in_simplified_flow(self):
        result = validate_affiliate_link(
            "https://pay.cakto.com.br/ANUAL123?affiliate=abc"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.plan, "annual")

    def test_bare_cakto_url_is_normalized(self):
        result = validate_affiliate_link(
            "pay.cakto.com.br/SEM123?affiliate=abc"
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.plan, "semiannual")

    def test_invite_link_gets_specific_guidance(self):
        result = validate_affiliate_link(
            "https://app.cakto.com.br/affiliate/invite/example"
        )
        self.assertFalse(result.ok)
        self.assertIn("convite", result.message)
        self.assertIn("link pessoal", result.message)

    def test_wrong_plan(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/ANUAL123?affiliate=abc",
            "monthly",
        )
        self.assertFalse(result.ok)
        self.assertIn("Anual", result.message)

    def test_other_product(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/OUTRO999?affiliate=abc",
            "monthly",
        )
        self.assertFalse(result.ok)
        self.assertIn("lista oficial", result.message)

    def test_fake_domain(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br.evil.example/MENSAL123?affiliate=abc",
            "monthly",
        )
        self.assertFalse(result.ok)

    def test_non_standard_port(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br:444/MENSAL123?affiliate=abc",
            "monthly",
        )
        self.assertFalse(result.ok)

    def test_extra_path_is_rejected(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123/extra?affiliate=abc",
            "monthly",
        )
        self.assertFalse(result.ok)

    def test_missing_affiliate(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123",
            "monthly",
        )
        self.assertFalse(result.ok)
        self.assertIn("identificador", result.message)

    def test_duplicate_affiliate_is_rejected(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123?affiliate=abc&affiliate=def",
            "monthly",
        )
        self.assertFalse(result.ok)

    def test_conflicting_affiliate_keys_are_rejected(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123?affiliate=abc&ref=abc",
            "monthly",
        )
        self.assertFalse(result.ok)

    def test_ref_supported(self):
        result = validate_checkout_link(
            "https://pay.cakto.com.br/MENSAL123?ref=abc",
            "monthly",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.affiliate_key, "ref")

    def test_duplicate_checkout_configuration_is_rejected(self):
        os.environ["CHECKOUT_ANNUAL"] = "MENSAL123"
        self.assertTrue(any("mais de um plano" in error for error in configuration_errors()))


if __name__ == "__main__":
    unittest.main()
