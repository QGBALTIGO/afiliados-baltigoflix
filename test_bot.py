import os
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from bot import ask_plan, support_text


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

    async def test_plan_prompt_uses_safe_support_text(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        await ask_plan(SimpleNamespace(message=message), "monthly")

        text = message.reply_text.await_args.args[0]
        options = message.reply_text.await_args.kwargs
        self.assertIn(r"@BaltigoFlix\_suporte", text)
        self.assertEqual(options["parse_mode"], "Markdown")


if __name__ == "__main__":
    unittest.main()
