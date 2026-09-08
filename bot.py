import html
import logging
import os
import re
import sqlite3
from urllib.parse import urlencode

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
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
from validator import PLAN_CONFIG, configuration_errors, validate_checkout_link


logger = logging.getLogger(__name__)
ASK_SLUG, ASK_MONTHLY, ASK_QUARTERLY, ASK_SEMIANNUAL, ASK_ANNUAL = range(5)


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
    if official_site:
        return official_site.rstrip("/") + "/?" + urlencode({"afiliado": slug})
    return env("PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/") + "/" + slug


def support_text(*, markdown: bool = False) -> str:
    username = env("SUPPORT_USERNAME", "@seu_suporte")
    if markdown:
        username = escape_markdown(username, version=1)
    return f"🆘 Atendimento humano: {username}"


def main_menu() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton("🚀 Criar minha página", callback_data="create")],
        [
            InlineKeyboardButton("💡 Como funciona", callback_data="how"),
            InlineKeyboardButton("💰 Comissões", callback_data="commissions"),
        ],
        [
            InlineKeyboardButton("📖 Pegar links", callback_data="tutorial"),
            InlineKeyboardButton("🌐 Minha página", callback_data="my_page"),
        ],
        [InlineKeyboardButton("🆘 Suporte", callback_data="support")],
    ]
    invite = env("AFFILIATE_INVITE_URL")
    if invite.startswith("https://"):
        buttons.insert(1, [InlineKeyboardButton("🤝 Quero ser afiliado", url=invite)])
    return InlineKeyboardMarkup(buttons)


def back_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Voltar ao menu", callback_data="menu")]])


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    brand = env("BRAND_NAME", "Minha Marca")
    text = (
        f"🤝 *{brand} Parceiros*\n\n"
        "Crie sua página personalizada de indicação em poucos passos.\n\n"
        "✅ Gratuito\n"
        "✅ Checkouts oficiais\n"
        "✅ Página personalizada\n"
        "✅ Aprovação administrativa\n"
        "✅ O pós-venda fica com a equipe oficial\n\n"
        "Escolha uma opção:"
    )
    await update.effective_message.reply_text(text, parse_mode="Markdown", reply_markup=main_menu())
    return ConversationHandler.END


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action = query.data

    if action == "menu":
        await query.edit_message_text("Escolha uma opção:", reply_markup=main_menu())
    elif action == "how":
        await query.edit_message_text(
            "💡 *Como funciona*\n\n"
            "1. Você entra no programa de afiliados.\n"
            "2. A plataforma de checkout gera seus links pessoais.\n"
            "3. O bot confere domínio, produto, plano e identificador.\n"
            "4. A equipe revisa o cadastro e aprova a página.\n"
            "5. Você divulga; o pós-venda fica com a equipe oficial.\n\n"
            "Não há promessa de renda: o resultado depende das vendas realizadas.",
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "commissions":
        await query.edit_message_text(
            "💰 *Níveis de comissão*\n\n"
            f"✅ Inicial: *{env('COMMISSION_INITIAL', '50%')}*\n"
            f"🚀 100 vendas: *{env('COMMISSION_100', '70%')}*\n"
            f"🔥 500 vendas: *{env('COMMISSION_500', '75%')}*\n\n"
            "Percentuais e elegibilidade seguem as regras oficiais da oferta e do checkout.",
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "tutorial":
        await query.edit_message_text(
            "📖 *Como pegar seus links*\n\n"
            "1️⃣ Entre na plataforma de checkout.\n"
            "2️⃣ Abra a área de afiliações.\n"
            "3️⃣ Localize o produto oficial.\n"
            "4️⃣ Abra a seção de links.\n"
            "5️⃣ Copie o link pessoal do plano solicitado.\n\n"
            "⚠️ Não envie link de convite, página genérica ou checkout de outro produto.\n\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
            reply_markup=back_menu(),
        )
    elif action == "support":
        await query.edit_message_text(
            "🆘 *Suporte humano*\n\n"
            "Este bot cuida apenas das ferramentas automáticas do parceiro.\n\n"
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
                        [InlineKeyboardButton("🔄 Reenviar links", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
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
                        [InlineKeyboardButton("🔄 Revalidar links", callback_data="create")],
                        [InlineKeyboardButton("⬅️ Voltar", callback_data="menu")],
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

    errors = configuration_errors()
    if not env_bool("AUTO_APPROVE_AFFILIATES") and not admin_ids():
        errors.append("Nenhum administrador foi configurado")
    if errors:
        await query.edit_message_text(
            "⚙️ O cadastro ainda não está disponível neste servidor.\n\n"
            + "\n".join(f"• {error}" for error in errors)
            + "\n\n"
            + support_text(),
            reply_markup=back_menu(),
        )
        return ConversationHandler.END

    context.user_data.clear()
    await query.edit_message_text(
        "🌐 *Escolha seu endereço público*\n\n"
        "Digite apenas o final da página. Seu nome completo do Telegram não será publicado.\n\n"
        "Exemplo: se você escrever `gabriel`, sua página ficará:\n"
        "`site.com/gabriel`\n\n"
        "Use de 3 a 30 caracteres: letras, números e hífen.\n\n"
        "Envie /cancel para cancelar.",
        parse_mode="Markdown",
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
            "Exemplo: `gabriel-tv`",
            parse_mode="Markdown",
        )
        return ASK_SLUG

    if not slug_available(slug, update.effective_user.id):
        await update.message.reply_text("❌ Esse endereço já está reservado ou em uso. Escolha outro.")
        return ASK_SLUG

    context.user_data["slug"] = slug
    context.user_data["links"] = {}
    await ask_plan(update, "monthly")
    return ASK_MONTHLY


async def ask_plan(update: Update, plan: str):
    label = PLAN_CONFIG[plan][0]
    await update.message.reply_text(
        f"🔗 *Plano {label}*\n\n"
        f"Cole agora seu link pessoal de checkout do plano *{label}*.\n\n"
        "Vou conferir domínio, oferta, plano e formato do identificador.\n\n"
        + support_text(markdown=True),
        parse_mode="Markdown",
    )


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, row) -> None:
    username = f"@{row['telegram_username']}" if row["telegram_username"] else "sem @username"
    text = (
        "🛡️ <b>Novo afiliado aguardando revisão</b>\n\n"
        f"Usuário: {html.escape(username)}\n"
        f"Telegram ID: <code>{row['telegram_user_id']}</code>\n"
        f"Slug: <code>{html.escape(row['slug'])}</code>\n"
        f"Affiliate ID: <code>{html.escape(row['affiliate_id'])}</code>\n\n"
        "Confirme a identidade e a autorização na plataforma antes de aprovar."
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


async def handle_plan(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    plan: str,
    next_plan: str | None,
    next_state: int | None,
):
    result = validate_checkout_link(update.message.text, plan)
    if not result.ok:
        await update.message.reply_text(
            "❌ *Não consegui aceitar esse link.*\n\n"
            + result.message
            + "\n\nTente novamente ou envie /cancel.\n"
            + support_text(markdown=True),
            parse_mode="Markdown",
        )
        return {
            "monthly": ASK_MONTHLY,
            "quarterly": ASK_QUARTERLY,
            "semiannual": ASK_SEMIANNUAL,
            "annual": ASK_ANNUAL,
        }[plan]

    links = context.user_data.setdefault("links", {})
    links[plan] = {
        "affiliate_id": result.affiliate_id,
        "affiliate_key": result.affiliate_key,
        "checkout_id": result.checkout_id,
    }

    identifiers = {value["affiliate_id"] for value in links.values()}
    if len(identifiers) > 1:
        links.pop(plan, None)
        await update.message.reply_text(
            "⚠️ *Identificador diferente*\n\n"
            "Esse link usa um afiliado diferente dos links anteriores. Por segurança, ele não foi aceito.",
            parse_mode="Markdown",
        )
        return {
            "monthly": ASK_MONTHLY,
            "quarterly": ASK_QUARTERLY,
            "semiannual": ASK_SEMIANNUAL,
            "annual": ASK_ANNUAL,
        }[plan]

    await update.message.reply_text(f"✅ {PLAN_CONFIG[plan][0]} validado.")
    if next_plan:
        await ask_plan(update, next_plan)
        return next_state

    slug = context.user_data.get("slug")
    if not slug or len(links) != len(PLAN_CONFIG):
        context.user_data.clear()
        await update.message.reply_text(
            "A sessão ficou incompleta. Inicie novamente com /start.",
            reply_markup=main_menu(),
        )
        return ConversationHandler.END

    user = update.effective_user
    affiliate_id = next(iter(identifiers))
    keys = {key: value["affiliate_key"] for key, value in links.items()}
    checkout_ids = {key: value["checkout_id"] for key, value in links.items()}
    auto_approve = env_bool("AUTO_APPROVE_AFFILIATES")
    try:
        row = save_affiliate(
            telegram_user_id=user.id,
            telegram_username=user.username,
            display_name=slug,
            slug=slug,
            affiliate_id=affiliate_id,
            keys=keys,
            checkout_ids=checkout_ids,
            active=auto_approve,
        )
    except sqlite3.IntegrityError:
        logger.exception("Conflito ao salvar slug %s", slug)
        await update.message.reply_text(
            "Esse endereço acabou de ser reservado por outra pessoa. Use /start e escolha outro."
        )
        context.user_data.clear()
        return ConversationHandler.END

    context.user_data.clear()
    url = page_url(slug)
    if auto_approve:
        await update.message.reply_text(
            "🎉 *Página criada!*\n\n"
            f"`{url}`\n\n"
            "Os checkouts são reconstruídos pelo servidor usando as ofertas configuradas.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🌐 Abrir minha página", url=url)],
                    [InlineKeyboardButton("🏠 Menu", callback_data="menu")],
                ]
            ),
        )
    else:
        await notify_admins(context, row)
        await update.message.reply_text(
            "🛡️ *Cadastro enviado para revisão*\n\n"
            f"Seu endereço reservado é `{url}`.\n\n"
            "A página será liberada depois que a equipe confirmar seu cadastro na plataforma de afiliados.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🏠 Menu", callback_data="menu")]]
            ),
        )
    return ConversationHandler.END


async def receive_monthly(update, context):
    return await handle_plan(update, context, "monthly", "quarterly", ASK_QUARTERLY)


async def receive_quarterly(update, context):
    return await handle_plan(update, context, "quarterly", "semiannual", ASK_SEMIANNUAL)


async def receive_semiannual(update, context):
    return await handle_plan(update, context, "semiannual", "annual", ASK_ANNUAL)


async def receive_annual(update, context):
    return await handle_plan(update, context, "annual", None, None)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.effective_message.reply_text("Operação cancelada.", reply_markup=main_menu())
    return ConversationHandler.END


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text(
        f"Seu Telegram ID é: `{update.effective_user.id}`", parse_mode="Markdown"
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
                "✅ *Sua página foi aprovada!*\n\n" + f"`{url}`",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("🌐 Abrir página", url=url)]]
                ),
            )
        else:
            await context.bot.send_message(
                telegram_user_id,
                "🚫 Seu cadastro foi bloqueado. Entre em contato com o suporte para mais informações.",
            )
    except Exception:
        logger.exception("Falha ao notificar afiliado %s", telegram_user_id)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Erro não tratado durante atualização", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "Ocorreu um erro inesperado. Tente novamente com /start."
            )
        except Exception:
            logger.exception("Não foi possível enviar a mensagem de erro")


def build_application() -> Application:
    token = env("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN não configurado")

    app = Application.builder().token(token).build()
    conversation = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CallbackQueryHandler(begin_create, pattern=r"^create$"),
        ],
        states={
            ASK_SLUG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_slug)],
            ASK_MONTHLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_monthly)],
            ASK_QUARTERLY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_quarterly)],
            ASK_SEMIANNUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_semiannual)],
            ASK_ANNUAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_annual)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(
                end_and_dispatch_menu,
                pattern=r"^(menu|how|commissions|tutorial|support|my_page)$",
            ),
        ],
        allow_reentry=True,
    )

    # O ConversationHandler precisa vir primeiro para que /cancel e os botões
    # também encerrem corretamente uma conversa em andamento.
    app.add_handler(conversation)
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("meuid", my_id))
    app.add_handler(CallbackQueryHandler(admin_action, pattern=r"^admin:(approve|block):\d+$"))
    app.add_handler(CallbackQueryHandler(menu_callback))
    app.add_error_handler(error_handler)
    return app
