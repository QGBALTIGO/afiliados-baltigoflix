import html
import os
from contextlib import asynccontextmanager
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from database import database_healthy, get_affiliate_by_slug, init_db
from validator import build_canonical_checkout, configuration_errors


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def official_site_url() -> str:
    return env("OFFICIAL_SITE_URL", "https://baltigoflix.com.br").rstrip("/")


def affiliate_public_url(slug: str) -> str:
    return official_site_url() + "/?" + urlencode({"afiliado": slug})


def official_site_origin() -> str:
    parsed = urlsplit(official_site_url())
    return f"{parsed.scheme}://{parsed.netloc}"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Baltigo Afiliados",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=lifespan,
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:; "
        "font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    )
    origin = request.headers.get("origin")
    if request.url.path.startswith("/api/") and origin == official_site_origin():
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


def support_markup() -> str:
    support = env("SUPPORT_USERNAME", "@seu_suporte")
    escaped = html.escape(support)
    if re_username := support.removeprefix("@").strip():
        if support.startswith("@") and re_username.replace("_", "").isalnum():
            return f'<a href="https://t.me/{html.escape(re_username)}">{escaped}</a>'
    return escaped


def layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#0b0e14">
<title>{html.escape(title)}</title>
<style>
:root {{
  color-scheme:dark; --bg:#090c12; --card:#141a24; --muted:#a8b0bd;
  --text:#f6f8fc; --line:#293142; --accent:#8067f5; --accent2:#59ddb3;
}}
* {{ box-sizing:border-box }}
body {{
  margin:0; font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;
  background:radial-gradient(circle at 50% -15%,#312663 0,#111523 35%,var(--bg) 70%);
  color:var(--text); min-height:100vh;
}}
a {{ color:inherit }}
.wrap {{ width:min(1040px,100%); margin:0 auto; padding:32px 18px 64px }}
.hero {{ padding:48px 0 28px; text-align:center }}
.badge {{
  display:inline-flex; align-items:center; padding:8px 13px; border:1px solid #384257;
  border-radius:999px; color:var(--accent2); background:#111722cc; font-size:14px;
}}
h1 {{ font-size:clamp(36px,8vw,68px); letter-spacing:-.045em; margin:18px 0 12px; line-height:.98 }}
.lead {{ max-width:660px; margin:0 auto; color:var(--muted); line-height:1.65; font-size:17px }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:14px; margin-top:30px }}
.card {{
  position:relative; background:linear-gradient(180deg,#192130,#111720); border:1px solid var(--line);
  border-radius:20px; padding:21px; box-shadow:0 18px 48px #0005; transition:.2s ease;
}}
.card:hover {{ transform:translateY(-3px); border-color:#6757b4 }}
.card h2 {{ margin:0 0 8px; font-size:20px }}
.offer {{ color:var(--muted); margin:0; font-size:14px }}
.price {{ font-size:29px; font-weight:850; margin:17px 0 3px; letter-spacing:-.03em }}
.btn {{
  display:block; text-decoration:none; text-align:center; color:white;
  background:linear-gradient(135deg,var(--accent),#5e47de); padding:13px 14px;
  border-radius:12px; font-weight:800; margin-top:18px; box-shadow:0 8px 20px #5e47de44;
}}
.trust {{
  margin-top:30px; padding:20px; border:1px solid var(--line); border-radius:17px;
  background:#10151ecc; text-align:center; line-height:1.6;
}}
.trust small {{ color:var(--muted) }}
.trust a {{ color:var(--accent2); text-decoration:none }}
@media(max-width:800px) {{ .grid {{ grid-template-columns:1fr 1fr }} }}
@media(max-width:500px) {{ .wrap {{ padding-inline:14px }} .grid {{ grid-template-columns:1fr }} .hero {{ padding-top:35px }} }}
</style>
</head>
<body>
<main class="wrap">
{body}
<footer class="trust">
  <strong>Atendimento oficial: {support_markup()}</strong><br>
  <small>Os botões usam somente ofertas configuradas pela equipe oficial.</small>
</footer>
</main>
</body>
</html>"""


@app.get("/health")
async def health():
    if not database_healthy():
        return JSONResponse({"status": "unhealthy", "database": "error"}, status_code=503)
    return {"status": "ok", "database": "ok"}


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots():
    return "User-agent: *\nDisallow: /\n"


@app.get("/", response_class=HTMLResponse)
async def home():
    brand = env("BRAND_NAME", "Minha Marca")
    brand_html = html.escape(brand)
    errors = configuration_errors()
    status = "Sistema online" if not errors else "Configuração em andamento"
    return layout(
        brand,
        f"""<section class="hero">
        <span class="badge">{html.escape(status)}</span>
        <h1>{brand_html}</h1>
        <p class="lead">Páginas oficiais do programa de parceiros. Cada endereço é liberado após a revisão do cadastro.</p>
        </section>""",
    )


def affiliate_checkouts(row) -> dict[str, str]:
    keys = {
        "monthly": row["monthly_key"],
        "quarterly": row["quarterly_key"],
        "semiannual": row["semiannual_key"],
        "annual": row["annual_key"],
    }
    checkout_ids = {
        "monthly": row["monthly_checkout"],
        "quarterly": row["quarterly_checkout"],
        "semiannual": row["semiannual_checkout"],
        "annual": row["annual_checkout"],
    }
    return {
        plan: build_canonical_checkout(
            plan,
            row["affiliate_id"],
            keys[plan],
            checkout_ids[plan],
        )
        for plan in ("monthly", "quarterly", "semiannual", "annual")
    }


@app.get("/api/affiliate/{slug}")
async def affiliate_api(slug: str):
    row = get_affiliate_by_slug(slug.lower())
    if not row:
        raise HTTPException(status_code=404, detail="Página não encontrada")
    try:
        checkouts = affiliate_checkouts(row)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail="Checkouts indisponíveis") from exc
    return JSONResponse(
        {"slug": row["slug"], "checkouts": checkouts},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/{slug}", response_class=RedirectResponse)
async def affiliate_page(slug: str):
    row = get_affiliate_by_slug(slug.lower())
    if not row:
        raise HTTPException(status_code=404, detail="Página não encontrada")
    return RedirectResponse(affiliate_public_url(row["slug"]), status_code=302)
