import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import (
    ask_affiliate_link,
    checkout_profile,
    main_menu,
    page_url,
    support_text,
    support_url,
    welcome_text,
)
from validator import validate_affiliate_link


class BotFormattingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ["SUPPORT_USERNAME"] = "@BaltigoFlix_suporte"
        os.environ["ALLOWED_CHECKOUT_HOSTS"] = "pay.cakto.com.br"
        os.environ["CHECKOUT_MONTHLY"] = "MENSAL123"
        os.environ["CHECKOUT_QUARTERLY"] = "TRI123,TRI456"
        os.environ["CHECKOUT_SEMIANNUAL"] = "SEM123"
        os.environ["CHECKOUT_ANNUAL"] = "ANUAL123"

    def tearDown(self):
        for name in (
            "SUPPORT_USERNAME",
            "ALLOWED_CHECKOUT_HOSTS",
            "CHECKOUT_MONTHLY",
            "CHECKOUT_QUARTERLY",
            "CHECKOUT_SEMIANNUAL",
            "CHECKOUT_ANNUAL",
            "OFFICIAL_SITE_URL",
            "OFFICIAL_SITE_INTEGRATION_ENABLED",
        ):
            os.environ.pop(name, None)

    def test_support_username_is_escaped_for_markdown(self):
        self.assertEqual(
            support_text(markdown=True),
            r"🆘 Atendimento humano: @BaltigoFlix\_suporte",
        )

    def test_support_username_becomes_a_direct_telegram_url(self):
        self.assertEqual(support_url(), "https://t.me/BaltigoFlix_suporte")

    def test_welcome_and_menu_explain_the_program(self):
        self.assertIn("Ganhe dinheiro", welcome_text())
        labels = [button.text for row in main_menu().inline_keyboard for button in row]
        self.assertIn("💸 Como ganho dinheiro?", labels)
        self.assertIn("❓ O que é a Cakto?", labels)
        self.assertIn("🆘 Falar com o suporte", labels)

    def test_page_url_uses_the_official_site(self):
        os.environ["OFFICIAL_SITE_URL"] = "https://baltigoflix.com.br/"
        os.environ["OFFICIAL_SITE_INTEGRATION_ENABLED"] = "true"
        self.assertEqual(
            page_url("gabriel-92"),
            "https://baltigoflix.com.br/?afiliado=gabriel-92",
        )

    def test_one_link_expands_to_all_four_plans(self):
        result = validate_affiliate_link(
            "https://pay.cakto.com.br/TRI456?affiliate=abc-123"
        )
        self.assertTrue(result.ok)

        keys, checkout_ids = checkout_profile(result)

        self.assertEqual(set(keys), {"monthly", "quarterly", "semiannual", "annual"})
        self.assertEqual(set(keys.values()), {"affiliate"})
        self.assertEqual(checkout_ids["monthly"], "MENSAL123")
        self.assertEqual(checkout_ids["quarterly"], "TRI456")
        self.assertEqual(checkout_ids["semiannual"], "SEM123")
        self.assertEqual(checkout_ids["annual"], "ANUAL123")

    async def test_single_link_prompt_mentions_support_and_four_plans(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        await ask_affiliate_link(SimpleNamespace(message=message))

        text = message.reply_text.await_args.args[0]
        options = message.reply_text.await_args.kwargs
        self.assertIn("somente um link", text)
        self.assertIn("quatro planos", text)
        self.assertIn(r"@BaltigoFlix\_suporte", text)
        self.assertEqual(options["parse_mode"], "Markdown")


if __name__ == "__main__":
    unittest.main()
