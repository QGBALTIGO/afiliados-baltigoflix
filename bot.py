import html
import logging
import os
import re
import sqlite3
from urllib.parse import urlencode

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
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
        return InlineKeyboardButton("💬 Falar com o suporte", url=url)
    return InlineKeyboardButton("💬 Falar com o suporte", callback_data="support")


def support_note() -> str:
    return "<i>Precisa de ajuda? Nossa equipe está disponível no botão abaixo.</i>"


def affiliate_invite_url() -> str | None:
    value = env("AFFILIATE_INVITE_URL")
    return value if value.startswith("https://") else None


def onboarding_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🔐 Acessar a Cakto",
                    url="https://app.cakto.com.br/",
                )
            ],
            [InlineKeyboardButton("✅ Já acessei minha conta", callback_data="onboarding_invite")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
            [support_button()],
        ]
    )


def onboarding_invite_keyboard() -> InlineKeyboardMarkup:
    rows = []
    invite = affiliate_invite_url()
    if invite:
        rows.append([InlineKeyboardButton("🔗 Abrir convite oficial", url=invite)])
    rows.extend(
        [
            [InlineKeyboardButton("✅ Convite aceito — continuar", callback_data="onboarding_profile")],
            [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
            [support_button()],
        ]
    )
    return InlineKeyboardMarkup(rows)


def main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🚀 Iniciar meu cadastro", callback_data="create")],
        [
            InlineKeyboardButton("ℹ️ Como funciona", callback_data="earnings"),
            InlineKeyboardButton("💰 Comissões", callback_data="commissions"),
        ],
        [
            InlineKeyboardButton("🏦 Sobre a Cakto", callback_data="cakto"),
            InlineKeyboardButton("🌐 Minha página", callback_data="my_page"),
        ],
        [InlineKeyboardButton("📖 Guia de cadastro", callback_data="tutorial")],
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
            [InlineKeyboardButton("✖️ Cancelar cadastro", callback_data="menu")],
            [support_button()],
        ]
    )


def welcome_text() -> str:
    brand = env("BRAND_NAME", "Baltigo")
    return (
        f"<b>{html.escape(brand.upper())} PARCEIROS</b>\n"
        "<i>Programa oficial de afiliados</i>\n\n"
        "Indique a BaltigoFlix, compartilhe sua página personalizada e receba comissão "
        "por cada venda válida realizada por meio dela.\n\n"
        "<b>Você recebe</b>\n"
        "• uma página exclusiva para divulgação;\n"
        "• identificação automática das suas vendas;\n"
        "• comissão registrada na Cakto;\n"
        "• suporte da equipe BaltigoFlix.\n\n"
        "O cadastro é gratuito e leva apenas alguns minutos.\n\n"
        "<i>Selecione uma opção para continuar.</i>"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        welcome_text(), parse_mode="HTML", reply_markup=main_menu()
    )
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "menu":
        await query.edit_message_text(
            welcome_text(), parse_mode="HTML", reply_markup=main_menu()
        )
    elif action == "earnings":
        await query.edit_message_text(
            "<b>COMO FUNCIONA</b>\n\n"
            "Ao concluir o cadastro, você recebe uma página personalizada da BaltigoFlix. "
            "Ela pode ser divulgada em canais, grupos, redes sociais ou diretamente aos seus contatos.\n\n"
            "<b>O processo é simples</b>\n"
            "1. O cliente acessa sua página.\n"
            "2. Escolhe um dos planos disponíveis.\n"
            "3. Finaliza o pagamento no checkout oficial.\n"
            "4. A Cakto identifica sua indicação.\n"
            "5. A comissão é registrada na sua conta.\n\n"
            "A equipe BaltigoFlix realiza a liberação do serviço e atende o comprador. "
            "Sua responsabilidade é a divulgação.\n\n"
            "<i>Os ganhos dependem das vendas aprovadas. Cancelamentos, reembolsos ou "
            "contestações podem alterar a comissão.</i>\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
    elif action == "cakto":
        await query.edit_message_text(
            "<b>SOBRE A CAKTO</b>\n\n"
            "A Cakto é a plataforma de pagamentos utilizada pela BaltigoFlix. É nela que "
            "sua afiliação é vinculada e suas comissões são registradas.\n\n"
            "<b>Na sua conta Cakto você poderá</b>\n"
            "• aceitar o convite da BaltigoFlix;\n"
            "• obter seu link pessoal de afiliado;\n"
            "• acompanhar vendas e comissões;\n"
            "• consultar prazos e solicitar saques.\n\n"
            "A criação da conta é gratuita. Você não precisa comprar uma assinatura para participar.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
    elif action == "commissions":
        await query.edit_message_text(
            "<b>COMISSÕES</b>\n\n"
            f"<b>Nível inicial</b> — {html.escape(env('COMMISSION_INITIAL', '50%'))}\n"
            f"<b>A partir de 100 vendas</b> — {html.escape(env('COMMISSION_100', '70%'))}\n"
            f"<b>A partir de 500 vendas</b> — {html.escape(env('COMMISSION_500', '75%'))}\n\n"
            "São consideradas as vendas válidas e aprovadas. O valor final da comissão, "
            "o prazo de liberação e as condições de saque ficam disponíveis na Cakto.\n\n"
            "A progressão de nível é conferida pela equipe BaltigoFlix.\n\n"
            "<i>Os percentuais indicam a regra do programa e não representam garantia de renda.</i>\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
    elif action == "tutorial":
        await query.edit_message_text(
            "<b>GUIA DE CADASTRO</b>\n\n"
            "<b>1. Acesse a Cakto</b>\n"
            "Crie sua conta gratuita ou entre em uma conta existente.\n\n"
            "<b>2. Aceite o convite</b>\n"
            "Retorne ao bot, abra o convite oficial da BaltigoFlix e confirme a afiliação.\n\n"
            "<b>3. Escolha seu endereço</b>\n"
            "Defina o nome que será usado na sua página personalizada.\n\n"
            "<b>4. Envie um único link</b>\n"
            "Na Cakto, copie o link pessoal de qualquer plano BaltigoFlix e envie ao bot. "
            "Os demais planos serão configurados automaticamente.\n\n"
            "O link correto começa com <code>https://pay.cakto.com.br/</code>. "
            "O link do convite não serve nesta etapa.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🚀 Iniciar cadastro", callback_data="create")],
                    [InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    elif action == "onboarding_invite":
        invite = affiliate_invite_url()
        if not invite:
            await query.edit_message_text(
                "<b>Convite indisponível</b>\n\n"
                "Não foi possível abrir o convite neste momento. Fale com nossa equipe para continuar.",
                parse_mode="HTML",
                reply_markup=back_menu(),
            )
            return
        await query.edit_message_text(
            "<b>CADASTRO · ETAPA 2 DE 4</b>\n"
            "<b>Aceite o convite da BaltigoFlix</b>\n\n"
            "Abra o convite oficial e confirme sua participação no programa de afiliados.\n\n"
            "Se a Cakto solicitar o login, acesse sua conta, retorne a esta conversa e abra "
            "o convite novamente.\n\n"
            "Depois da confirmação, selecione <b>“Convite aceito — continuar”</b>.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=onboarding_invite_keyboard(),
        )
    elif action == "support":
        await query.edit_message_text(
            "<b>CENTRAL DE AJUDA</b>\n\n"
            "Nossa equipe pode ajudar com cadastro na Cakto, aceite do convite, localização "
            "do link pessoal, comissões e uso da página de divulgação.\n\n"
            "Ao entrar em contato, informe em qual etapa encontrou dificuldade. Se possível, "
            "envie também uma captura da tela.\n\n"
            f"<b>Atendimento:</b> {html.escape(env('SUPPORT_USERNAME', '@seu_suporte'))}",
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
    elif action == "my_page":
        row = get_affiliate_by_telegram(query.from_user.id)
        if not row:
            await query.edit_message_text(
                "<b>MINHA PÁGINA</b>\n\n"
                "Você ainda não possui uma página cadastrada. Inicie o cadastro para criar "
                "seu endereço personalizado.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🚀 Iniciar cadastro", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
                        [support_button()],
                    ]
                ),
            )
        elif not row["active"]:
            await query.edit_message_text(
                "<b>MINHA PÁGINA</b>\n"
                "<i>Aguardando aprovação</i>\n\n"
                f"<b>Endereço reservado</b>\n<code>{html.escape(page_url(row['slug']))}</code>\n\n"
                "A equipe está conferindo sua afiliação na Cakto. Você receberá uma mensagem "
                "assim que a página for liberada.\n\n"
                + support_note(),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("✏️ Atualizar cadastro", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
                        [support_button()],
                    ]
                ),
            )
        else:
            url = page_url(row["slug"])
            await query.edit_message_text(
                "<b>MINHA PÁGINA</b>\n"
                "<i>Cadastro aprovado</i>\n\n"
                f"<code>{html.escape(url)}</code>\n\n"
                "Compartilhe este endereço. As vendas realizadas por meio dele serão "
                "identificadas com seus dados de afiliado.\n\n"
                + support_note(),
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🌐 Abrir minha página", url=url)],
                        [InlineKeyboardButton("✏️ Atualizar cadastro", callback_data="create")],
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
            "<b>CADASTRO · ETAPA 1 DE 4</b>\n"
            "<b>Acesse sua conta Cakto</b>\n\n"
            "A Cakto registra suas vendas, calcula as comissões e disponibiliza o saldo "
            "de acordo com as regras da plataforma.\n\n"
            "Crie uma conta gratuitamente ou entre em uma conta existente. Quando concluir, "
            "retorne a esta conversa e selecione <b>“Já acessei minha conta”</b>.\n\n"
            "<i>Não é necessário comprar uma assinatura para participar.</i>\n\n"
            + support_note(),
            parse_mode="HTML",
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
            "<b>Cadastro temporariamente indisponível</b>\n\n"
            "Não foi possível iniciar o cadastro agora. Fale com nossa equipe para receber ajuda.",
            parse_mode="HTML",
            reply_markup=back_menu(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "<b>CADASTRO · ETAPA 3 DE 4</b>\n"
        "<b>Escolha o endereço da sua página</b>\n\n"
        "Digite o nome que deseja utilizar no endereço público. Seu nome completo do Telegram "
        "não será exibido.\n\n"
        "<b>Exemplo</b>\n"
        "Nome escolhido: <code>gabriel</code>\n"
        "Página: <code>baltigoflix.com.br/?afiliado=gabriel</code>\n\n"
        "Use entre 3 e 30 caracteres, somente letras sem acento, números e hífen.\n\n"
        + support_note(),
        parse_mode="HTML",
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
            "<b>Endereço inválido</b>\n\n"
            "Use entre 3 e 30 caracteres, somente letras sem acento, números e hífen.\n\n"
            "Exemplo válido: <code>gabriel-tv</code>\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_SLUG

    if not slug_available(slug, update.effective_user.id):
        await update.message.reply_text(
            "<b>Endereço indisponível</b>\n\n"
            "Esse nome já está reservado. Escolha outra opção para continuar.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_SLUG

    context.user_data["slug"] = slug
    await ask_affiliate_link(update)
    return ASK_AFFILIATE_LINK


async def ask_affiliate_link(update: Update):
    await update.message.reply_text(
        "<b>CADASTRO · ETAPA 4 DE 4</b>\n"
        "<b>Envie seu link pessoal</b>\n\n"
        "Na Cakto, acesse o produto BaltigoFlix na área de afiliações e copie o seu link "
        "de divulgação de qualquer plano.\n\n"
        "<b>Formato esperado</b>\n"
        "<code>https://pay.cakto.com.br/...</code>\n\n"
        "Envie apenas um link. O sistema identificará seus dados e configurará automaticamente "
        "os demais planos.\n\n"
        "<i>O link do convite não é um link de divulgação.</i>\n\n"
        + support_note(),
        parse_mode="HTML",
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
            "<b>Não foi possível validar o link</b>\n\n"
            + html.escape(result.message)
            + "\n\nConfira o endereço na Cakto e envie novamente.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=cancel_support_keyboard(),
        )
        return ASK_AFFILIATE_LINK

    slug = context.user_data.get("slug")
    if not slug:
        context.user_data.clear()
        await update.message.reply_text(
            "<b>Sessão encerrada</b>\n\n"
            "Use /start para iniciar um novo cadastro ou fale com o suporte.",
            parse_mode="HTML",
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
            "<b>Endereço indisponível</b>\n\n"
            "Esse nome foi reservado durante o cadastro. Use /start para escolher outro endereço.",
            parse_mode="HTML",
            reply_markup=main_menu(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()
    url = page_url(slug)
    if auto_approve:
        await update.message.reply_text(
            "<b>CADASTRO CONCLUÍDO</b>\n\n"
            "Sua página foi criada e os quatro planos foram configurados com seus dados de afiliado.\n\n"
            f"<b>Seu endereço</b>\n<code>{html.escape(url)}</code>\n\n"
            "Compartilhe essa página para começar a divulgar a BaltigoFlix.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🌐 Abrir minha página", url=url)],
                    [InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    else:
        await notify_admins(context, row, result.plan)
        await update.message.reply_text(
            "<b>CADASTRO RECEBIDO</b>\n"
            "<i>Aguardando análise</i>\n\n"
            "Seu link foi validado e os quatro planos foram configurados. Agora a equipe "
            "confirmará sua afiliação na Cakto.\n\n"
            f"<b>Endereço reservado</b>\n<code>{html.escape(url)}</code>\n\n"
            "Você será avisado assim que a página estiver disponível.\n\n"
            + support_note(),
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")],
                    [support_button()],
                ]
            ),
        )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        "<b>Cadastro cancelado</b>\n\nVocê pode iniciar novamente quando desejar.",
        parse_mode="HTML",
        reply_markup=main_menu(),
    )
    return ConversationHandler.END


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"<b>Seu ID do Telegram</b>\n\n<code>{update.effective_user.id}</code>",
        parse_mode="HTML",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text(
        "<b>CENTRAL DE AJUDA</b>\n\n"
        "Consulte o guia de cadastro no menu ou fale diretamente com nossa equipe. "
        "Informe em qual etapa encontrou dificuldade e, se possível, envie uma captura da tela.\n\n"
        + support_note(),
        parse_mode="HTML",
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
                "<b>CADASTRO APROVADO</b>\n\n"
                "Sua página já está disponível para divulgação.\n\n"
                f"<b>Seu endereço</b>\n<code>{html.escape(url)}</code>\n\n"
                "As vendas realizadas por meio dessa página serão identificadas com seus dados "
                "de afiliado e registradas na Cakto.\n\n"
                + support_note(),
                parse_mode="HTML",
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
                "<b>CADASTRO NÃO APROVADO</b>\n\n"
                "Não foi possível aprovar seus dados neste momento. Fale com nossa equipe "
                "para verificar o motivo e receber orientação.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup([[support_button()]]),
            )
    except Exception:
        logger.exception("Falha ao notificar afiliado %s", telegram_user_id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro não tratado durante atualização", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "<b>Não foi possível concluir esta ação</b>\n\n"
                "Tente novamente usando /start. Se o problema continuar, fale com nossa equipe.",
                parse_mode="HTML",
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
