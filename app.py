import logging
import os
import threading

import uvicorn
from dotenv import load_dotenv

# Carrega o .env antes de importar módulos que leem configuração.
load_dotenv()

from bot import build_application
from database import init_db


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_web() -> None:
    uvicorn.run(
        "webapp:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", "8000")),
        reload=False,
        log_level=os.getenv("LOG_LEVEL", "info").lower(),
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


if __name__ == "__main__":
    init_db()

    # Permite que o Railway publique a página de configuração antes de o token
    # ser cadastrado. Assim que TELEGRAM_BOT_TOKEN existir, um redeploy também
    # inicia o polling do bot.
    if not os.getenv("TELEGRAM_BOT_TOKEN", "").strip():
        logger.warning("TELEGRAM_BOT_TOKEN ausente; iniciando somente o servidor web")
        run_web()
        raise SystemExit(0)

    # O polling do Telegram permanece no processo principal para receber sinais
    # corretamente. A API web atende o health check e as páginas em outra thread.
    web_thread = threading.Thread(target=run_web, name="web-server", daemon=True)
    web_thread.start()

    application = build_application()
    logger.info("Bot e servidor web iniciados")
    application.run_polling(drop_pending_updates=True)
