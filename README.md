# Baltigo Afiliados

Bot do Telegram que cadastra parceiros, confere links de checkout e cria páginas públicas personalizadas.

## Fluxo

1. O parceiro cria ou acessa gratuitamente sua conta Cakto.
2. Abre novamente o convite BaltigoFlix e aceita a afiliação.
3. Escolhe um identificador público, como `gabriel`.
4. Envia somente um link pessoal de qualquer plano oficial.
5. O bot extrai o identificador de afiliado e monta automaticamente os quatro checkouts.
6. Um administrador verifica a identidade e a autorização na Cakto.
7. Após a aprovação, o site oficial abre com `?afiliado=gabriel` e recebe da API somente os checkouts reconstruídos pelo servidor.

> A validação automática confere o formato do link. A aprovação humana continua necessária enquanto não houver integração oficial com a API do gateway.

## Recursos de segurança

- Domínio e IDs de checkout em allowlist.
- Rejeição de plano, produto, porta ou caminho inesperado.
- Identificadores duplicados ou conflitantes são rejeitados.
- Os links brutos enviados não são armazenados.
- Um único link pessoal configura Mensal, Trimestral, Semestral e Anual.
- Links sem `https://` também são reconhecidos quando começam com `pay.cakto.com.br`.
- Links do convite ou do painel recebem uma orientação específica em vez de um erro genérico.
- Consultas SQL parametrizadas e saída HTML escapada.
- Aprovação e bloqueio somente por administradores configurados.
- Nome completo do Telegram não é publicado.
- Cabeçalhos CSP, HSTS, anti-frame e política de permissões.
- SQLite com WAL, espera contra bloqueios e caminho configurável.

## Instalação local

Requer Python 3.12 ou mais recente.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m unittest discover -v
python app.py
```

No Windows, ative o ambiente com:

```bat
.venv\Scripts\activate
```

## Configuração obrigatória

Copie `.env.example` para `.env` e configure:

- `TELEGRAM_BOT_TOKEN`: token novo do BotFather.
- `ADMIN_TELEGRAM_IDS`: IDs numéricos dos administradores, separados por vírgula.
- `PUBLIC_BASE_URL`: domínio HTTPS público.
- `OFFICIAL_SITE_URL`: endereço do site verdadeiro que exibirá os links do afiliado.
- `OFFICIAL_SITE_INTEGRATION_ENABLED`: ativa os links do site oficial somente depois que a integração está publicada; mantenha `false` durante a preparação.
- `AFFILIATE_INVITE_URL`: convite oficial de afiliação da BaltigoFlix na Cakto.
- `SUPPORT_USERNAME`: usuário do Telegram do suporte; o bot cria botões diretos em todas as etapas.
- `CHECKOUT_MONTHLY`: ID ou IDs do checkout mensal.
- `CHECKOUT_QUARTERLY`: ID ou IDs do checkout trimestral.
- `CHECKOUT_SEMIANNUAL`: ID ou IDs do checkout semestral.
- `CHECKOUT_ANNUAL`: ID ou IDs do checkout anual.

Quando um plano tiver mais de um checkout oficial, separe os IDs por vírgula, por exemplo: `3fsy24d,35znaim`. Se o único link enviado pelo afiliado usar uma dessas opções, o bot preserva esse checkout; nos demais planos, usa a primeira opção oficial configurada.

O comando `/meuid` mostra o ID numérico do usuário no Telegram.

O site oficial consulta `GET /api/affiliate/{slug}` no serviço do Railway. O endpoint só responde para cadastros aprovados e libera CORS exclusivamente para `OFFICIAL_SITE_URL`. Quando `OFFICIAL_SITE_INTEGRATION_ENABLED=true`, links antigos no formato do Railway (`/{slug}`) redirecionam para o site oficial.

Nunca envie ou publique o token do bot. Se um token já apareceu em chat, commit, print ou log, revogue-o no BotFather.

## Aprovação

Quando o cadastro é concluído, cada administrador recebe os botões `Aprovar` e `Bloquear`, o plano usado na validação e o identificador encontrado. Uma página pendente responde como não encontrada e só é publicada após a aprovação.

Para testes internos, `AUTO_APPROVE_AFFILIATES=true` desativa essa revisão. Não é recomendado em produção.

## Railway

O arquivo `railway.toml` define o comando de inicialização, health check e política de reinício.

Variáveis recomendadas em produção:

```env
HOST=0.0.0.0
DB_PATH=/data/affiliate_pages.db
AUTO_APPROVE_AFFILIATES=false
```

Monte um volume persistente em `/data`; sem ele, os cadastros serão perdidos quando o container for recriado.

O Railway fornece `PORT` automaticamente.

Sem `TELEGRAM_BOT_TOKEN`, o serviço permanece online somente com a página web e o health check. Depois que o token for configurado, um novo deploy inicia também o bot.

## Limitações atuais

- A propriedade do identificador ainda precisa ser conferida pelo administrador no gateway.
- Não há painel web administrativo.
- Não há métricas de visitas, cliques ou vendas.
- O SQLite é adequado para este MVP, mas uma operação maior deve migrar para PostgreSQL.
