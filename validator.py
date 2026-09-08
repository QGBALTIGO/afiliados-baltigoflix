import os
import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse


URL_RE = re.compile(r"https?://[^\s<>\]\[\"']+", re.I)
CHECKOUT_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,160}")
AFFILIATE_ID_RE = re.compile(r"[A-Za-z0-9._:@+-]{1,128}")
AFFILIATE_KEYS = ("affiliate", "ref")

PLAN_CONFIG = {
    "monthly": ("Mensal", "CHECKOUT_MONTHLY"),
    "quarterly": ("Trimestral", "CHECKOUT_QUARTERLY"),
    "semiannual": ("Semestral", "CHECKOUT_SEMIANNUAL"),
    "annual": ("Anual", "CHECKOUT_ANNUAL"),
}


@dataclass
class ValidationResult:
    ok: bool
    message: str
    plan: str | None = None
    affiliate_id: str | None = None
    affiliate_key: str | None = None
    checkout_id: str | None = None


def official_checkouts() -> dict[str, str]:
    result = {}
    for plan, (_, env_name) in PLAN_CONFIG.items():
        value = os.getenv(env_name, "").strip().strip("/")
        if value:
            result[plan] = value
    return result


def allowed_hosts() -> set[str]:
    raw = os.getenv("ALLOWED_CHECKOUT_HOSTS", "pay.cakto.com.br")
    return {host.strip().lower().rstrip(".") for host in raw.split(",") if host.strip()}


def configuration_errors() -> list[str]:
    errors = []
    checkouts = official_checkouts()
    missing = [label for plan, (label, _) in PLAN_CONFIG.items() if plan not in checkouts]
    if missing:
        errors.append("Checkouts ausentes: " + ", ".join(missing))

    invalid = [plan for plan, checkout_id in checkouts.items() if not CHECKOUT_ID_RE.fullmatch(checkout_id)]
    if invalid:
        errors.append("IDs de checkout inválidos: " + ", ".join(invalid))

    if len(set(checkouts.values())) != len(checkouts):
        errors.append("Os quatro planos precisam usar IDs de checkout diferentes")

    if not allowed_hosts():
        errors.append("Nenhum domínio de checkout permitido foi configurado")
    return errors


def extract_url(text: str) -> str | None:
    if not text:
        return None
    match = URL_RE.search(text.strip())
    if not match:
        return None
    return match.group(0).rstrip(".,;:!?)]}")


def detect_plan(checkout_id: str) -> str | None:
    for plan, configured_id in official_checkouts().items():
        if configured_id == checkout_id:
            return plan
    return None


def validate_checkout_link(text: str, expected_plan: str) -> ValidationResult:
    if expected_plan not in PLAN_CONFIG:
        return ValidationResult(False, "Plano solicitado inválido.")

    url = extract_url(text)
    if not url:
        return ValidationResult(False, "Não encontrei um link http/https na mensagem.")

    try:
        parsed = urlparse(url)
        port = parsed.port
    except ValueError:
        return ValidationResult(False, "O link não pôde ser interpretado.")

    if parsed.scheme.lower() != "https":
        return ValidationResult(False, "O checkout precisa usar HTTPS.")

    host = (parsed.hostname or "").lower().rstrip(".")
    if host not in allowed_hosts():
        return ValidationResult(False, "Esse domínio não está na lista de checkouts permitidos.")

    if port not in (None, 443):
        return ValidationResult(False, "O checkout usa uma porta não permitida.")

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 1:
        return ValidationResult(False, "O endereço do checkout possui um caminho inesperado.")

    checkout_id = parts[0]
    detected = detect_plan(checkout_id)
    if detected is None:
        return ValidationResult(
            False,
            "Esse checkout não pertence à lista oficial configurada.",
            checkout_id=checkout_id,
        )

    if detected != expected_plan:
        detected_label = PLAN_CONFIG[detected][0]
        expected_label = PLAN_CONFIG[expected_plan][0]
        return ValidationResult(
            False,
            f"Esse link é do plano {detected_label}, mas agora preciso do plano {expected_label}.",
            plan=detected,
            checkout_id=checkout_id,
        )

    query = parse_qs(parsed.query, keep_blank_values=True)
    populated_keys = []
    for key in AFFILIATE_KEYS:
        values = [value.strip() for value in query.get(key, []) if value.strip()]
        if values:
            populated_keys.append((key, values))

    if not populated_keys:
        return ValidationResult(
            False,
            "O checkout é oficial, mas não encontrei um identificador de afiliado (?affiliate=... ou ?ref=...).",
            plan=detected,
            checkout_id=checkout_id,
        )

    if len(populated_keys) != 1 or len(populated_keys[0][1]) != 1:
        return ValidationResult(False, "O link possui identificadores de afiliado duplicados ou conflitantes.")

    affiliate_key, values = populated_keys[0]
    affiliate_id = values[0]
    if not AFFILIATE_ID_RE.fullmatch(affiliate_id):
        return ValidationResult(False, "O identificador de afiliado possui formato inválido.")

    return ValidationResult(
        True,
        "Formato do link validado.",
        plan=detected,
        affiliate_id=affiliate_id,
        affiliate_key=affiliate_key,
        checkout_id=checkout_id,
    )


def build_canonical_checkout(plan: str, affiliate_id: str, affiliate_key: str = "affiliate") -> str:
    checkouts = official_checkouts()
    checkout_id = checkouts.get(plan)
    if not checkout_id:
        raise ValueError(f"Checkout oficial não configurado para {plan}")
    if affiliate_key not in AFFILIATE_KEYS:
        raise ValueError("Chave de afiliado inválida")
    if not AFFILIATE_ID_RE.fullmatch(affiliate_id):
        raise ValueError("Identificador de afiliado inválido")
    hosts = sorted(allowed_hosts())
    if not hosts:
        raise ValueError("Nenhum domínio de checkout configurado")
    query = urlencode({affiliate_key: affiliate_id})
    return urlunparse(("https", hosts[0], f"/{checkout_id}", "", query, ""))
