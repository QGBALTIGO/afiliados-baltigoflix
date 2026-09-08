import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).with_name("affiliate_pages.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS affiliates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    telegram_username TEXT,
    display_name TEXT,
    slug TEXT NOT NULL UNIQUE,
    affiliate_id TEXT NOT NULL,
    monthly_key TEXT NOT NULL DEFAULT 'affiliate',
    quarterly_key TEXT NOT NULL DEFAULT 'affiliate',
    semiannual_key TEXT NOT NULL DEFAULT 'affiliate',
    annual_key TEXT NOT NULL DEFAULT 'affiliate',
    active INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_affiliates_slug_active
ON affiliates(slug, active);
"""

RESERVED = {
    "admin", "api", "login", "logout", "conta", "account", "app", "bot",
    "telegram", "suporte", "support", "oficial", "official", "checkout",
    "cakto", "static", "assets", "favicon.ico", "robots.txt", "health",
    "docs", "redoc", "openapi.json",
}


def database_path() -> Path:
    configured = os.getenv("DB_PATH", "").strip()
    return Path(configured).expanduser() if configured else DEFAULT_DB_PATH


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout=30000")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        con.execute("PRAGMA journal_mode=WAL")


def database_healthy() -> bool:
    try:
        with connect() as con:
            return con.execute("SELECT 1").fetchone()[0] == 1
    except sqlite3.Error:
        return False


def slug_available(slug: str, telegram_user_id: int | None = None) -> bool:
    if slug.lower() in RESERVED:
        return False
    with connect() as con:
        row = con.execute(
            "SELECT telegram_user_id FROM affiliates WHERE slug=?",
            (slug,),
        ).fetchone()
        if row is None:
            return True
        return telegram_user_id is not None and row["telegram_user_id"] == telegram_user_id


def get_affiliate_by_telegram(telegram_user_id: int):
    with connect() as con:
        return con.execute(
            "SELECT * FROM affiliates WHERE telegram_user_id=?",
            (telegram_user_id,),
        ).fetchone()


def get_affiliate_by_slug(slug: str):
    with connect() as con:
        return con.execute(
            "SELECT * FROM affiliates WHERE slug=? AND active=1",
            (slug,),
        ).fetchone()


def save_affiliate(
    telegram_user_id: int,
    telegram_username: str | None,
    display_name: str,
    slug: str,
    affiliate_id: str,
    keys: dict[str, str],
    active: bool = False,
):
    with connect() as con:
        con.execute(
            """
            INSERT INTO affiliates (
                telegram_user_id, telegram_username, display_name, slug, affiliate_id,
                monthly_key, quarterly_key, semiannual_key, annual_key, active
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                telegram_username=excluded.telegram_username,
                display_name=excluded.display_name,
                slug=excluded.slug,
                affiliate_id=excluded.affiliate_id,
                monthly_key=excluded.monthly_key,
                quarterly_key=excluded.quarterly_key,
                semiannual_key=excluded.semiannual_key,
                annual_key=excluded.annual_key,
                active=excluded.active,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                telegram_user_id,
                telegram_username,
                display_name,
                slug,
                affiliate_id,
                keys.get("monthly", "affiliate"),
                keys.get("quarterly", "affiliate"),
                keys.get("semiannual", "affiliate"),
                keys.get("annual", "affiliate"),
                int(active),
            ),
        )
    return get_affiliate_by_telegram(telegram_user_id)


def set_affiliate_active(telegram_user_id: int, active: bool):
    with connect() as con:
        cursor = con.execute(
            """
            UPDATE affiliates
            SET active=?, updated_at=CURRENT_TIMESTAMP
            WHERE telegram_user_id=?
            """,
            (int(active), telegram_user_id),
        )
        if cursor.rowcount == 0:
            return None
    return get_affiliate_by_telegram(telegram_user_id)
