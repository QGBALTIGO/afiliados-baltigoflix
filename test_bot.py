import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import ask_plan, page_url, support_text


class BotFormattingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        os.environ["SUPPORT_USERNAME"] = "@BaltigoFlix_suporte"

    def tearDown(self):
        os.environ.pop("SUPPORT_USERNAME", None)

    def test_support_username_is_escaped_for_markdown(self):
        self.assertEqual(
            support_text(markdown=True),
            r"🆘 Atendimento humano: @BaltigoFlix\_suporte",
        )

    def test_page_url_uses_the_official_site(self):
        os.environ["OFFICIAL_SITE_URL"] = "https://baltigoflix.com.br/"
        try:
            self.assertEqual(
                page_url("gabriel-92"),
                "https://baltigoflix.com.br/?afiliado=gabriel-92",
            )
        finally:
            os.environ.pop("OFFICIAL_SITE_URL", None)

    async def test_plan_prompt_uses_safe_support_text(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        await ask_plan(SimpleNamespace(message=message), "monthly")

        text = message.reply_text.await_args.args[0]
        options = message.reply_text.await_args.kwargs
        self.assertIn(r"@BaltigoFlix\_suporte", text)
        self.assertEqual(options["parse_mode"], "Markdown")


if __name__ == "__main__":
    unittest.main()
