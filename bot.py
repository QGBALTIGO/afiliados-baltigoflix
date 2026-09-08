import html
import logging
import os
import re
import sqlite3
from urllib.parse import urlencode

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.helpers import escape_markdown
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from database import (
    get_affiliate_by_telegram,
    save_affiliate,
    set_affiliate_active,
    slug_available,
)
from validator import (
    PLAN_CONFIG,
    configuration_errors,
    official_checkouts,
    validate_affiliate_link,
)


logger = logging.getLogger(__name__)
ASK_SLUG, ASK_AFFILIATE_LINK = range(2)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def env_bool(name: str, default: bool = False) -> bool:
    value = env(name, "true" if default else "false").lower()
    return value in {"1", "true", "yes", "sim", "on"}


def admin_ids() -> set[int]:
    result = set()
    for value in re.split(r"[,;\s]+", env("ADMIN_TELEGRAM_IDS")):
        if value.isdigit():
            result.add(int(value))
    return result


def page_url(slug: str) -> str:
    official_site = env("OFFICIAL_SITE_URL", "https://baltigoflix.com.br")
    if env_bool("OFFICIAL_SITE_INTEGRATION_ENABLED") and official_site:
        return official_site.rstrip("/") + "/?" + urlencode({"afiliado": slug})
    return env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/" + slug


def support_text(*, markdown: bool = False) -> str:
    username = env("SUPPORT_USERNAME", "@seu_suporte")
    if markdown:
        username = escape_markdown(username, version=1)
    return f"🆘 Atendimento humano: {username}"


def support_url() -> str | None:
    value = env("SUPPORT_USERNAME", "@seu_suporte")
    if value.startswith(("https://", "http://")):
        return value
    username = value.lstrip("@").strip()
    if re.fullmatch(r"[A-Za-z0-9_]{5,32}", username):
        return f"https://t.me/{username}"
    return None


def support_button() -> InlineKeyboardButton:
    url = support_url()
    if url:
        return InlineKeyboardButton("🆘 Falar com o suporte", url=url)
    return InlineKeyboardButton("🆘 Falar com o suporte", callback_data="support")


def affiliate_invite_url() -> str | None:
    value = env("AFFILIATE_INVITE_URL")
    return value if value.startswith("https://") else None


def onboarding_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "1️⃣ Criar ou entrar na Cakto",
                    url="https://app.cakto.com.br/",
                )
            ],
            [InlineKeyboardButton("➡️ Já entrei na Cakto", callback_data="onboarding_invite")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
            [support_button()],
        ]
    )


def onboarding_invite_keyboard() -> InlineKeyboardMarkup:
    rows = []
    invite = affiliate_invite_url()
    if invite:
        rows.append([InlineKeyboardButton("2️⃣ Aceitar convite BaltigoFlix", url=invite)])
    rows.extend(
        [
            [InlineKeyboardButton("✅ Já aceitei o convite", callback_data="onboarding_profile")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
            [support_button()],
        ]
    )
    return InlineKeyboardMarkup(rows)


def main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🚀 Quero começar", callback_data="create")],
        [
            InlineKeyboardButton("💸 Como ganho dinheiro?", callback_data="earnings"),
        ],
        [
            InlineKeyboardButton("❓ O que é a Cakto?", callback_data="cakto"),
            InlineKeyboardButton("💰 Comissões", callback_data="commissions"),
        ],
        [
            InlineKeyboardButton("📖 Passo a passo", callback_data="tutorial"),
            InlineKeyboardButton("🌐 Minha página", callback_data="my_page"),
        ],
        [support_button()],
    ]
    return InlineKeyboardMarkup(buttons)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")],
            [support_button()],
        ]
    )


def cancel_support_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("❌ Cancelar e voltar", callback_data="menu")],
            [support_button()],
        ]
    )


def welcome_text() -> str:
    brand = env("BRAND_NAME", "Baltigo")
    return (
        f"🤝 *Programa de Afiliados {escape_markdown(brand, version=1)}*\n\n"
        "Ganhe dinheiro indicando a BaltigoFlix. Você recebe uma página personalizada, "
        "divulga para outras pessoas e recebe comissão pelas vendas aprovadas.\n\n"
        "✅ Cadastro gratuito\n"
        "✅ Não precisa atender o cliente\n"
        "✅ Pagamentos e comissões pela Cakto\n"
        "✅ Sua própria página da BaltigoFlix\n\n"
        "Não sabe como funciona? Sem problema: o bot explica cada etapa e o suporte pode ajudar."
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        welcome_text(), parse_mode="Markdown", reply_markup=main_menu()
    )
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "menu":
        await query.edit_message_text(
            welcome_text(), parse_mode="Markdown", reply_markup=main_menu()
        )
    elif action == "earnings":
        await query.edit_message_text(
            "💸 *Como você ganha dinheiro?*\n\n"
            "1️⃣ Você recebe uma página personalizada da BaltigoFlix.\n"
            "2️⃣ Divulga essa página nos seus canais, grupos ou redes sociais.\n"
            "3️⃣ A pessoa escolhe um plano e paga pelo checkout oficial.\n"
            "4️⃣ A Cakto identifica que a venda veio de você e registra sua comissão.\n"
            "5️⃣ O saldo e as regras de saque ficam disponíveis na sua conta Cakto.\n\n"
            "A equipe BaltigoFlix cuida da liberação e do atendimento ao comprador. "
            "Você cuida apenas da divulgação.\n\n"
            "⚠️ Não existe ganho garantido: você recebe quando realiza vendas válidas e aprovadas. "
            "Reembolsos ou cancelamentos podem retirar a comissão.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "cakto":
        await query.edit_message_text(
            "❓ *O que é a Cakto?*\n\n"
            "A Cakto é a plataforma de pagamentos usada pela BaltigoFlix. Ela é separada "
            "do Telegram e funciona como a sua carteira de afiliado.\n\n"
            "Na Cakto você:\n"
            "• cria sua conta gratuitamente;\n"
            "• aceita o convite da BaltigoFlix;\n"
            "• recebe seu identificador pessoal;\n"
            "• acompanha vendas e comissões;\n"
            "• solicita o saque conforme as regras da plataforma.\n\n"
            "Você não precisa comprar nenhum plano para ser afiliado.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "commissions":
        await query.edit_message_text(
            "💰 *Níveis de comissão*\n\n"
            f"🌱 Ao começar: *{env('COMMISSION_INITIAL', '50%')}*\n"
            f"🚀 Ao atingir 100 vendas: *{env('COMMISSION_100', '70%')}*\n"
            f"🔥 Ao atingir 500 vendas: *{env('COMMISSION_500', '75%')}*\n\n"
            "A comissão é calculada sobre vendas válidas conforme a configuração da oferta. "
            "O valor final, o prazo de liberação e o saque aparecem na Cakto.\n\n"
            "Mudanças de nível são conferidas pela equipe. Os percentuais não são promessa de renda.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "tutorial":
        await query.edit_message_text(
            "📖 *Passo a passo completo*\n\n"
            "1️⃣ Toque em “Quero começar”.\n"
            "2️⃣ Crie sua conta gratuita na Cakto ou faça login.\n"
            "3️⃣ Volte ao bot e abra novamente o convite BaltigoFlix.\n"
            "4️⃣ Aceite o convite de afiliação.\n"
            "5️⃣ Na Cakto, abra a BaltigoFlix na área de produtos afiliados.\n"
            "6️⃣ Copie *somente um* link pessoal de qualquer plano.\n"
            "7️⃣ Envie esse link ao bot e escolha o nome da sua página.\n"
            "8️⃣ Aguarde a conferência da equipe.\n\n"
            "O link correto começa com `https://pay.cakto.com.br/` e possui seu identificador "
            "de afiliado. Não envie o link de convite.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🚀 Começar agora", callback_data="create")],
                    [InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    elif action == "onboarding_invite":
        invite = affiliate_invite_url()
        if not invite:
            await query.edit_message_text(
                "⚙️ O convite está temporariamente indisponível. Fale com o suporte para receber ajuda.",
                reply_markup=back_menu(),
            )
            return
        await query.edit_message_text(
            "🤝 *Etapa 2 de 3 — Aceite o convite*\n\n"
            "Agora abra o convite oficial da BaltigoFlix e confirme que deseja ser afiliado.\n\n"
            "⚠️ Se a Cakto pedir login novamente, entre na conta, volte a esta conversa e abra "
            "o convite mais uma vez. Isso evita que você fique apenas na tela inicial da Cakto.\n\n"
            "Depois de aceitar, volte aqui e toque em “Já aceitei o convite”.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=onboarding_invite_keyboard(),
        )
    elif action == "support":
        await query.edit_message_text(
            "🆘 *Suporte humano*\n\n"
            "Se tiver dúvida para criar a conta, aceitar o convite, encontrar seu link, "
            "acompanhar comissão ou usar sua página, fale com nossa equipe.\n\n"
            "Envie uma mensagem explicando em qual etapa parou e, se possível, uma captura da tela.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "my_page":
        row = get_affiliate_by_telegram(query.from_user.id)
        if not row:
            await query.edit_message_text(
                "Você ainda não criou uma página.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🚀 Criar agora", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
                        [support_button()],
                    ]
                ),
            )
        elif not row["active"]:
            await query.edit_message_text(
                "⏳ *Página aguardando aprovação*\n\n"
                f"Endereço reservado: `{page_url(row['slug'])}`\n\n"
                "Você receberá uma mensagem quando a equipe concluir a revisão.",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔄 Reenviar meu link", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
                        [support_button()],
                    ]
                ),
            )
        else:
            url = page_url(row["slug"])
            await query.edit_message_text(
                f"🌐 *Sua página*\n\n`{url}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🌐 Abrir página", url=url)],
                        [InlineKeyboardButton("🔄 Atualizar meu link", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
                        [support_button()],
                    ]
                ),
            )


async def end_and_dispatch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await menu_callback(update, context)
    return ConversationHandler.END


async def begin_create(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "create":
        context.user_data.clear()
        await query.edit_message_text(
            "🍀 *Etapa 1 de 3 — Entre na Cakto*\n\n"
            "A Cakto é a plataforma que registra suas vendas, calcula sua comissão e disponibiliza "
            "o saldo para saque. Criar a conta é gratuito.\n\n"
            "Toque no primeiro botão para criar sua conta ou fazer login. Quando terminar, volte "
            "a esta conversa e toque em “Já entrei na Cakto”.\n\n"
            "Você não precisa comprar uma assinatura para participar.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=onboarding_start_keyboard(),
        )
        return ConversationHandler.END

    errors = configuration_errors()
    if not env_bool("AUTO_APPROVE_AFFILIATES") and not admin_ids():
        errors.append("Nenhum administrador foi configurado")
    if not affiliate_invite_url():
        errors.append("Convite da Cakto não configurado")
    if errors:
        await query.edit_message_text(
            "⚙️ O cadastro está temporariamente indisponível. Nossa equipe já pode ajudar você.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "🌐 *Etapa 3 de 3 — Crie sua página*\n\n"
        "Primeiro, escolha o nome que aparecerá no endereço da sua página. Seu nome completo "
        "do Telegram não será publicado.\n\n"
        "Exemplo: se você escrever `gabriel`, sua página será:\n"
        "`baltigoflix.com.br/?afiliado=gabriel`\n\n"
        "Use de 3 a 30 caracteres: letras, números e hífen.\n\n"
        "Digite o nome desejado agora.\n\n"
        + support_text(markdown=True),
        parse_mode="Markdown",
        reply_markup=cancel_support_keyboard(),
    )
    return ASK_SLUG


def normalize_slug(text: str) -> str | None:
    slug = text.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,28}[a-z0-9]", slug):
        return None
    if "--" in slug:
        return None
    return slug


async def receive_slug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    slug = normalize_slug(update.message.text)
    if not slug:
        await update.message.reply_text(
            "❌ Esse endereço não é válido.\n\n"
            "Use de 3 a 30 caracteres, somente letras sem acento, números e hífen.\n"
            "Exemplo: `gabriel-tv`\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_SLUG

    if not slug_available(slug, update.effective_user.id):
        await update.message.reply_text(
            "❌ Esse endereço já está reservado. Escolha outro nome.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_SLUG

    context.user_data["slug"] = slug
    await ask_affiliate_link(update)
    return ASK_AFFILIATE_LINK


async def ask_affiliate_link(update: Update):
    await update.message.reply_text(
        "🔗 *Agora envie somente um link*\n\n"
        "Na Cakto, abra o produto BaltigoFlix na área de afiliações e copie seu link pessoal "
        "de qualquer plano: mensal, trimestral, semestral ou anual.\n\n"
        "O link correto começa com:\n"
        "`https://pay.cakto.com.br/`\n\n"
        "Cole o link completo aqui. O bot encontrará seu identificador e criará automaticamente "
        "os quatro planos — você não precisa copiar os outros links.\n\n"
        "⚠️ Não envie novamente o link do convite.\n\n"
        + support_text(markdown=True),
        parse_mode="Markdown",
        reply_markup=cancel_support_keyboard(),
    )


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, row, source_plan: str) -> None:
    username = f"@{row['telegram_username']}" if row["telegram_username"] else "sem @username"
    text = (
        "🛡️ <b>Novo afiliado aguardando revisão</b>\n\n"
        f"Usuário: {html.escape(username)}\n"
        f"Telegram ID: <code>{row['telegram_user_id']}</code>\n"
        f"Slug: <code>{html.escape(row['slug'])}</code>\n"
        f"Affiliate ID: <code>{html.escape(row['affiliate_id'])}</code>\n\n"
        f"Link validado: plano {html.escape(PLAN_CONFIG[source_plan][0])}\n"
        "Os quatro checkouts foram gerados automaticamente.\n\n"
        "Confirme a identidade e a autorização na Cakto antes de aprovar."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Aprovar", callback_data=f"admin:approve:{row['telegram_user_id']}"
                ),
                InlineKeyboardButton(
                    "🚫 Bloquear", callback_data=f"admin:block:{row['telegram_user_id']}"
                ),
            ]
        ]
    )
    for telegram_id in admin_ids():
        try:
            await context.bot.send_message(
                telegram_id, text, parse_mode="HTML", reply_markup=keyboard
            )
        except Exception:
            logger.exception("Falha ao notificar administrador %s", telegram_id)


def checkout_profile(result) -> tuple[dict[str, str], dict[str, str]]:
    configured = official_checkouts()
    keys = {plan: result.affiliate_key for plan in PLAN_CONFIG}
    checkout_ids = {plan: configured[plan][0] for plan in PLAN_CONFIG}
    checkout_ids[result.plan] = result.checkout_id
    return keys, checkout_ids


async def receive_affiliate_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = validate_affiliate_link(update.message.text)
    if not result.ok:
        await update.message.reply_text(
            "❌ *Ainda não consegui validar esse link*\n\n"
            + result.message
            + "\n\nCopie novamente o link pessoal na Cakto e envie aqui.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_AFFILIATE_LINK

    slug = context.user_data.get("slug")
    if not slug:
        context.user_data.clear()
        await update.message.reply_text(
            "A sessão expirou. Use /start para começar novamente.\n\n" + support_text(),
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    user = update.effective_user
    keys, checkout_ids = checkout_profile(result)
    auto_approve = env_bool("AUTO_APPROVE_AFFILIATES")
    try:
        row = save_affiliate(
            telegram_user_id=user.id,
            telegram_username=user.username,
            display_name=slug,
            slug=slug,
            affiliate_id=result.affiliate_id,
            keys=keys,
            checkout_ids=checkout_ids,
            active=auto_approve,
        )
    except sqlite3.IntegrityError:
        logger.exception("Conflito ao salvar slug %s", slug)
        await update.message.reply_text(
            "Esse endereço acabou de ser reservado por outra pessoa. Use /start e escolha outro.\n\n"
            + support_text(),
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()
    url = page_url(slug)
    if auto_approve:
        await update.message.reply_text(
            "🎉 *Tudo pronto! Sua página foi criada*\n\n"
            f"`{url}`\n\n"
            "O bot usou seu único link para configurar automaticamente os quatro planos. "
            "Agora você pode divulgar essa página e receber comissão pelas vendas aprovadas.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🌐 Abrir minha página", url=url)],
                    [InlineKeyboardButton("🏠 Menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    else:
        await notify_admins(context, row, result.plan)
        await update.message.reply_text(
            "✅ *Link validado e cadastro enviado*\n\n"
            "O bot encontrou seu identificador e configurou automaticamente os quatro planos.\n\n"
            f"Seu endereço reservado é `{url}`.\n\n"
            "Agora a equipe confirmará sua afiliação na Cakto. Você receberá uma mensagem quando "
            "a página for liberada.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🏠 Voltar ao menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("Operação cancelada.", reply_markup=main_menu())
    return ConversationHandler.END


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Seu Telegram ID é: `{update.effective_user.id}`", parse_mode="Markdown"
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        "🆘 *Precisa de ajuda?*\n\n"
        "Você pode usar o passo a passo do menu ou falar diretamente com nossa equipe. "
        "Informe em qual etapa parou e envie uma captura da tela, se possível.\n\n"
        + support_text(markdown=True),
        parse_mode="Markdown",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


async def configure_bot(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Abrir o menu de afiliados"),
            BotCommand("ajuda", "Ver ajuda e falar com o suporte"),
            BotCommand("cancelar", "Cancelar o cadastro atual"),
            BotCommand("meuid", "Mostrar seu ID do Telegram"),
        ]
    )


async def admin_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in admin_ids():
        await query.answer("Ação permitida somente para administradores.", show_alert=True)
        return

    try:
        _, action, raw_user_id = query.data.split(":", 2)
        telegram_user_id = int(raw_user_id)
    except (ValueError, AttributeError):
        await query.answer("Ação inválida.", show_alert=True)
        return

    active = action == "approve"
    if action not in {"approve", "block"}:
        await query.answer("Ação inválida.", show_alert=True)
        return

    row = set_affiliate_active(telegram_user_id, active)
    if not row:
        await query.answer("Cadastro não encontrado.", show_alert=True)
        return

    await query.answer("Cadastro atualizado.")
    status = "✅ APROVADO" if active else "🚫 BLOQUEADO"
    await query.edit_message_text(
        f"{status}\n\n"
        f"Telegram ID: <code>{row['telegram_user_id']}</code>\n"
        f"Slug: <code>{html.escape(row['slug'])}</code>",
        parse_mode="HTML",
    )
    try:
        if active:
            url = page_url(row["slug"])
            await context.bot.send_message(
                telegram_user_id,
                "🎉 *Sua página foi aprovada!*\n\n"
                f"`{url}`\n\n"
                "Agora é só divulgar este endereço. Quando alguém assinar por ele, a Cakto "
                "identificará sua indicação e registrará a comissão.\n\n"
                + support_text(markdown=True),
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🌐 Abrir minha página", url=url)],
                        [support_button()],
                    ]
                ),
            )
        else:
            await context.bot.send_message(
                telegram_user_id,
                "🚫 Seu cadastro não pôde ser aprovado neste momento. Fale com o suporte para "
                "entender o motivo e corrigir o que for necessário.",
                reply_markup=InlineKeyboardMarkup([[support_button()]]),
            )
    except Exception:
        logger.exception("Falha ao notificar afiliado %s", telegram_user_id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro não tratado durante atualização", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Ocorreu um erro inesperado. Tente novamente com /start ou fale com o suporte.",
                reply_markup=main_menu(),
            )
        except Exception:
            logger.exception("Não foi possível enviar a mensagem de erro")


def build_application() -> Application:
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")

    app = Application.builder().token(token).post_init(configure_bot).build()
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(begin_create, pattern=r"^(create|onboarding_profile)$"),
        ],
        states={
            ASK_SLUG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_slug)],
            ASK_AFFILIATE_LINK: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_affiliate_link)
            ],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CommandHandler("cancelar", cancel),
            CommandHandler("ajuda", help_command),
            CallbackQueryHandler(
                end_and_dispatch_menu,
                pattern=r"^(menu|earnings|cakto|commissions|tutorial|support|my_page|onboarding_invite)$",
            ),
        ],
        allow_reentry=True,
    )

    # O ConversationHandler precisa vir primeiro para que /cancel e os botões
    # também encerrem corretamente uma conversa em andamento.
    app.add_handler(conversation)
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("cancelar", cancel))
    app.add_handler(CommandHandler("ajuda", help_command))
    app.add_handler(CommandHandler("meuid", my_id))
    app.add_handler(CallbackQueryHandler(admin_action, pattern=r"^admin:(approve|block):\d+$"))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_error_handler(error_handler)
    return app
