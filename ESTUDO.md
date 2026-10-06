# Task API (Flask) — Anotações de estudo

> **Data:** 2026-10-06 · **Stack:** Python 3.12+ · Flask 3 · Pydantic 2 · PyJWT + bcrypt · SQLite · pytest · Ruff ·
> Docker · GitHub Actions

---

## 1. Visão geral

API REST de **gerenciamento de tarefas** (to-do list): cada usuário cria uma conta, faz login, recebe um token JWT e
gerencia só as próprias tarefas, com filtros, busca, ordenação e paginação.

O pedido inicial foi uma API simples, mas **sem pontas soltas**: todo erro tratado e sempre com uma resposta. Por
isso o foco do projeto é o **tratamento de erros completo**: qualquer falha (campo inválido, token vencido, JSON
quebrado, erro inesperado no servidor) devolve uma resposta JSON **sempre no mesmo formato**.

O objetivo foi ter **a mesma API em duas stacks**, em repositórios separados: primeiro `task-api-express`
(Node.js + Express), depois esta, em Python + Flask, com os mesmos endpoints, códigos de erro e mensagens. O
repositório `task-api-compose` sobe as duas juntas e prova, com um teste de contrato, que elas respondem igual.

Cada API tem o **próprio banco de usuários**, então os tokens **não** valem de uma para a outra. Isso é garantido
pelo campo `iss` do token (veja a Fase 12).

---

## 2. Arquitetura

Não tem frontend: é só o backend (API), consumido por qualquer cliente HTTP (Swagger UI, Postman, um app web...).

### Caminho de uma requisição

```mermaid
flowchart LR
    C[Cliente] --> S[Servidor HTTP<br/>Werkzeug ou waitress]
    S --> H1[before_request:<br/>request id → rate limit → leitura do JSON]
    H1 --> R[Rota<br/>blueprint]
    R --> G[login_required<br/>valida o JWT]
    G --> V[validate_request<br/>Pydantic]
    V --> SV[Service<br/>regras de negócio]
    SV --> RP[Repository<br/>SQL]
    RP --> DB[(SQLite)]
    R -. qualquer exceção .-> E[error handler<br/>JSON padrão]
```

### Camadas de cada módulo

| Camada | Responsabilidade | Exemplo |
|---|---|---|
| **routes** | Recebe a requisição HTTP, chama a validação e devolve a resposta | `tasks/routes.py` |
| **schemas** | Define o formato esperado dos dados (Pydantic) | `CreateTaskBody` |
| **service** | Regras de negócio (ex.: a tarefa é desse usuário?) | `TaskService._get_owned_task` |
| **repository** | Só acesso ao banco (SQL) | `TaskRepository.list` |

Separar assim deixa cada parte fácil de entender e testar. O service não sabe nada de HTTP, e o repository não sabe
nada de regras de negócio.

### Estrutura de pastas

```
main.py                 # ponto de entrada: sobe o servidor, trata sinais e erros de processo
app/
├── __init__.py         # create_app(): monta a aplicação (application factory)
├── config.py           # lê e valida as variáveis de ambiente
├── db.py               # conexões SQLite e criação das tabelas
├── errors.py           # AppError e atalhos (bad_request, not_found...)
├── error_handlers.py   # transforma QUALQUER exceção no JSON padrão
├── http_hooks.py       # request id, leitura do corpo, cabeçalhos de segurança
├── json_depth.py       # limite de aninhamento do JSON (checado antes do parse)
├── protocol_errors.py  # JSON também para erros que o servidor HTTP detecta antes do Flask
├── rate_limit.py       # limite de requisições por IP
├── validation.py       # integra o Pydantic e traduz as mensagens para português
├── logger.py           # log em JSON, uma linha por evento
├── clock.py            # data/hora no mesmo formato do JavaScript
├── docs/               # especificação OpenAPI + arquivos do Swagger UI
└── modules/
    ├── auth/           # cadastro, login, /me e o decorator login_required
    ├── tasks/          # CRUD de tarefas
    ├── users/          # acesso à tabela de usuários
    └── health/         # /health (a API e o banco estão de pé?)
tests/                  # 137 testes com pytest
.github/                # CI (workflows/ci.yml) e Dependabot (dependabot.yml)
Dockerfile, docker-compose.yml, .dockerignore   # empacotamento em container
.gitattributes          # quebras de linha LF em todos os sistemas
```

---

## 3. Fases e etapas

### Fase 1 — Base do projeto e configuração
- **Objetivo:** ter um projeto Python organizado que só sobe se estiver bem configurado.
- **O que foi feito:**
  1. Projeto criado com **uv** (`pyproject.toml` + `uv.lock`).
  2. `config.py` lê as variáveis de ambiente (`.env`) e valida cada uma: tipo, mínimo, máximo e formato (`1h`, `100kb`).
  3. Os problemas são **acumulados** e mostrados todos de uma vez (classe `_Reader`), em vez de parar no primeiro.
  4. `create_app(config, db)` monta a aplicação recebendo a configuração e o banco por parâmetro.
  5. Porta padrão **5000** (a do Express é 3000), para as duas APIs poderem rodar ao mesmo tempo.
- **Por quê:**
  - Validar a configuração na subida evita descobrir só em produção que o `JWT_SECRET` estava vazio.
  - Receber `config` e `db` por parâmetro (injeção de dependência) permite que os testes criem apps isolados com
    banco em memória.

### Fase 2 — Banco de dados
- **Objetivo:** guardar usuários e tarefas.
- **O que foi feito:**
  - Duas tabelas, `users` e `tasks`, com `FOREIGN KEY ... ON DELETE CASCADE`, `CHECK` nos campos `status` e
    `priority` e um índice em `tasks.user_id`.
  - Uma conexão por requisição: aberta quando é necessária (`get_conn`) e fechada no fim (`teardown_appcontext`).
  - Modo **WAL** no SQLite e `PRAGMA foreign_keys = ON` em cada conexão.
  - Suporte a `:memory:` com cache compartilhado, para os testes.
- **Por quê:**
  - O SQLite já vem com o Python (`sqlite3`): nenhum servidor de banco para instalar.
  - O `sqlite3` não deve ser compartilhado entre threads, por isso cada requisição tem a sua conexão.
  - O SQLite vem com as chaves estrangeiras **desligadas** por padrão; sem o PRAGMA, o `CASCADE` não funcionaria.

### Fase 3 — Tratamento de erros padronizado (o coração do projeto)
- **Objetivo:** toda resposta de erro no formato `{ "error": { status, code, message, details, requestId } }`.
- **O que foi feito:**
  1. `AppError`: uma exceção com status, código, mensagem, detalhes e cabeçalhos. Atalhos como `not_found()` e
     `unauthorized()` deixam o código mais legível.
  2. Um único `@app.errorhandler(Exception)` que converte **tudo** (`AppError`, erros do Werkzeug como 404/405/413 e
     exceções inesperadas) com `normalize_error()`.
  3. Erros 500 vão para o log com o stack trace. O cliente recebe só "Erro interno do servidor" (em desenvolvimento
     aparece também um campo `debug`).
  4. `requestId` em toda resposta e no cabeçalho `X-Request-Id`, para achar a requisição no log.
  5. `protocol_errors.py`: erros que o **servidor HTTP** detecta antes do Flask (requisição malformada, cabeçalhos
     gigantes) também saem em JSON, no Werkzeug e no waitress.
  6. Erros fora das requisições: configuração inválida, porta ocupada, exceções em threads e Ctrl+C/SIGTERM.
- **Por quê:**
  - O `code` é estável (`TASK_NOT_FOUND`) e serve para o programa cliente decidir o que fazer. A `message` é para
    humanos e pode mudar.
  - Nunca expor detalhes internos em produção: o stack trace revela a estrutura do código para um atacante.

### Fase 4 — Leitura do corpo e validação
- **Objetivo:** só deixar chegar às regras de negócio dados corretos, e explicar exatamente o que está errado.
- **O que foi feito:**
  - `http_hooks.py` confere `Content-Type`, charset (só UTF-8), `Content-Encoding` (aceita gzip/deflate), tamanho
    máximo e se o JSON é válido. Também rejeita `NaN`/`Infinity` e aceita só objeto ou array no corpo.
  - Proteção contra *zip bomb*: descompacta no máximo `limite + 1` bytes.
  - `validation.py`: os schemas Pydantic recebem camelCase no JSON (`dueDate`) e usam snake_case no Python
    (`due_date`). Campos desconhecidos são rejeitados (`extra="forbid"`).
  - As mensagens do Pydantic são traduzidas para português, com mensagens específicas por campo (`MESSAGES`), iguais
    às da versão Express.
  - `validate_request()` valida params, query e body juntos e devolve **todos** os problemas de uma vez em `details`.
- **Por quê:**
  - Devolver todos os erros de uma vez evita o cliente corrigir um campo, reenviar e descobrir o próximo erro.
  - `MISSING` (um objeto sentinela) diferencia "não mandou corpo" de "mandou `null`".

### Fase 5 — Autenticação (JWT + bcrypt)
- **Objetivo:** cadastro, login e proteção das rotas.
- **O que foi feito:**
  - `POST /auth/register` e `POST /auth/login` devolvem `accessToken`. `GET /auth/me` devolve o usuário logado.
  - A senha é guardada como hash **bcrypt**, nunca em texto puro.
  - JWT HS256 com `sub` (id do usuário), `iss` (emissor: `task-api-flask`), `iat` e `exp`. Na validação, `exp`,
    `sub` e `iss` são obrigatórios.
  - O decorator `login_required` lê `Authorization: Bearer <token>` e coloca o usuário em `g.user`.
  - E-mail normalizado (minúsculas, sem espaços) com a mesma regex do Zod usada na versão Express.
- **Decisões de segurança importantes:**
  - **Mesma resposta e mesmo tempo** para "e-mail não existe" e "senha errada". Quando o e-mail não existe, o código
    compara com um *hash fictício* (`_dummy_hash`), para que o tempo de resposta não revele quais e-mails têm conta.
  - **Limite de 72 bytes na senha**: o bcrypt ignora o que passa disso, um acento ocupa 2 bytes em UTF-8, e a
    biblioteca `bcrypt` do Python **lança exceção** acima do limite (sem a validação, viraria um erro 500).
  - O token de um usuário que foi apagado é rejeitado, porque o código busca o usuário no banco a cada requisição.
  - Um `sub` numérico gigante viraria `OverflowError` no SQLite (500); ele é validado com a mesma regra dos IDs.
  - Rate limit mais restrito nas rotas de autenticação (10 tentativas por 15 minutos), contra força bruta.

### Fase 6 — CRUD de tarefas
- **Objetivo:** criar, listar, buscar, atualizar e remover tarefas.
- **O que foi feito:**
  - `GET /tasks` com filtros (`status`, `priority`), busca (`search` no título e na descrição), paginação (`page`,
    `limit`) e ordenação (`sortBy`, `order`). A resposta traz `data` e `meta`.
  - `POST /tasks` devolve **201** e o cabeçalho `Location` com o endereço da nova tarefa.
  - `PATCH /tasks/:id` atualiza só os campos enviados (`exclude_unset`) e exige pelo menos um campo.
  - `DELETE` devolve **204** (sem corpo).
  - **404** quando a tarefa não existe e **403** quando ela pertence a outro usuário.
- **Por quê / detalhes:**
  - Todos os valores vão para o SQL como parâmetros (`?`), o que impede SQL injection. O `ORDER BY` não aceita
    parâmetros, então ele é escolhido de uma lista fechada (`ORDER_BY`).
  - `%` e `_` na busca são escapados (`_escape_like`), porque no `LIKE` eles são curingas.
  - Ao ordenar por `dueDate`, tarefas sem prazo ficam sempre no final. A ordenação por `priority` usa um `CASE`
    (low < medium < high) em vez da ordem alfabética.
  - 404 e 405 são respondidos **antes** de exigir o token: por isso o `login_required` está em cada rota, e não no
    blueprint inteiro. Essa é a mesma ordem de prioridade da versão Express.

### Fase 7 — Segurança HTTP
- **O que foi feito:**
  - **CORS** com `flask-cors`, expondo os cabeçalhos `X-Request-Id` e `Location`.
  - **Cabeçalhos de segurança** equivalentes aos do `helmet` do Express (CSP, `X-Frame-Options`, HSTS, ...).
  - **Rate limit próprio** (`RateLimiter`): janela fixa por IP, guardada em memória, com cabeçalhos `RateLimit` e
    `Retry-After` no padrão do IETF. O preflight de CORS (`OPTIONS`) não conta.
- **Por quê:** o `Flask-Limiter` foi considerado, mas o rate limit foi escrito à mão (cerca de 50 linhas) para ter
  controle total da resposta 429 (o JSON padrão, com `Retry-After`) e reproduzir o `express-rate-limit` da versão
  Express.

### Fase 8 — Documentação (OpenAPI + Swagger UI)
- **O que foi feito:** especificação OpenAPI 3 escrita em Python (`docs/openapi.py`) e servida em `/openapi.json`.
  A documentação interativa fica em `/docs`.
- **Segundo commit:** o pacote `swagger-ui-bundle` foi trocado pelos arquivos do **Swagger UI 5.33.1** copiados
  para dentro do projeto, com `StandaloneLayout` e botão de tema claro/escuro.
  - **Motivo:** o pacote Python parou na versão 4.x, que não tem tema escuro, e assim as duas versões (Flask e
    Express) usam o mesmo Swagger UI.
  - Só uma lista fechada de arquivos é servida (`STATIC_FILES`). Isso impede ler outros arquivos da pasta ou usar
    `../` para sair dela.
  - O script de inicialização fica num arquivo separado (`/docs/init.js`) porque a Content-Security-Policy bloqueia
    scripts inline.

### Fase 9 — Servidor e processo (`main.py`)
- **O que foi feito:**
  - `APP_ENV=development` usa o servidor do Werkzeug, que reinicia ao salvar um arquivo.
  - `APP_ENV=production` usa o **waitress**.
  - Saída do console em UTF-8 (evita erro ao logar acentos no Windows).
  - Mensagem clara quando a porta está ocupada ou sem permissão.
  - SIGTERM tratado como Ctrl+C: o servidor espera as requisições em andamento e fecha o banco.
- **Por quê:**
  - O waitress funciona no Windows. O gunicorn, servidor de produção mais comum em Python, só roda em Linux/macOS.
  - **`SO_EXCLUSIVEADDRUSE` no Windows:** a opção padrão (`SO_REUSEADDR`) deixava **dois processos** ouvirem a mesma
    porta sem nenhum erro. Veja a seção 7.

### Fase 10 — Testes
- **O que foi feito:** 137 testes com pytest, com relatório de cobertura pelo `pytest-cov` (cerca de 96%).
  - A fixture `make_app` cria um app novo com **banco em memória** para cada teste, então um teste não interfere no
    outro.
  - O helper `expect_error()` confere que cada erro segue exatamente o formato padrão.
  - `BCRYPT_ROUNDS=4` nos testes, para o hash não deixar a suíte lenta.
  - Os testes foram portados um a um dos testes do Express, para garantir o mesmo contrato.

### Fase 11 — Docker
- **O que foi feito:**
  - `Dockerfile` **multi-stage**: a primeira etapa instala as dependências com uv, e a imagem final não leva o uv nem
    ferramentas de build.
  - Dependências copiadas **antes** do código: o cache do Docker só refaz a instalação quando o `uv.lock` muda.
  - Roda com um usuário sem privilégios (`appuser`), tem `HEALTHCHECK` chamando `/health` e guarda o banco num
    volume (`flask-data`).
  - `docker-compose.yml` lê o `JWT_SECRET` do `.env` e falha com uma mensagem clara se ele não existir
    (`${JWT_SECRET:?...}`). Usa `init: true` e `stop_grace_period: 15s` para o encerramento controlado.
  - A imagem base é configurável (`ARG PYTHON_IMAGE`, padrão `python:3.14-slim`). Isso nasceu de um problema local:
    veja a seção 7.
  - O `uv` vem de um estágio próprio (`FROM ghcr.io/astral-sh/uv:... AS uv`), para o Dependabot conseguir atualizá-lo.

### Fase 12 — Correção de segurança: claim `iss`
- **Problema:** no teste com as duas APIs rodando juntas, um token emitido pelo **Flask** funcionou no **Express** e
  devolveu outro usuário. As duas compartilhavam o `JWT_SECRET`, mas cada uma tem o seu banco: o usuário `id = 1` é
  uma pessoa diferente em cada uma.
- **Solução:** o token passa a levar `iss: "task-api-flask"`, e a validação exige esse emissor. Um token da outra API
  (ou sem `iss`) dá `401 INVALID_TOKEN`, mesmo assinado com o mesmo segredo.
- **Lição:** a versão anterior deste arquivo dizia que os tokens eram "compatíveis" entre as APIs, como se fosse uma
  vantagem. Compartilhar tokens só é seguro quando os usuários também são compartilhados.

### Fase 13 — CI no GitHub Actions
- **O que foi feito:**
  - Job **Testes** na matriz Python 3.12, 3.13 e 3.14 (3.12 é o mínimo do `requires-python`; 3.14 é o do Docker).
  - Job **Imagem Docker**: build, sobe o container, espera o health check, testa um erro no formato padrão e confere
    que o `docker stop` termina com código 0.
  - `uv sync --locked`: o CI falha se o `uv.lock` estiver desatualizado em relação ao `pyproject.toml`.
- **Problema na primeira execução:** `astral-sh/setup-uv@v10` não existe. Essa action não publica a tag de versão
  principal (`v10`), só as completas (`v10.2.0`). Veja a seção 7.

### Fase 14 — Limite de aninhamento do JSON
- **Problema:** um teste com 50 mil níveis de `[[[...]]]` passava no Windows e falhava no CI (Linux, Python 3.14).
  No Windows o `json.loads` estourava a pilha (`RecursionError` → `INVALID_JSON`); no Linux a pilha é maior, o
  Python 3.14 conseguia ler tudo e a resposta virava `VALIDATION_ERROR`.
- **Solução:** `json_depth.py` recusa mais de **32 níveis**, contando `[`/`{` fora de strings nos **bytes**, antes do
  `json.loads`. O resultado deixa de depender da plataforma. O Express ganhou o mesmo limite, e o teste de contrato
  verifica os dois.

### Fase 15 — Dependabot e proteção da `main`
- **Dependabot** para `uv`, GitHub Actions e Docker: roda toda segunda, agrupa minor/patch num PR, espera 3 dias
  (7 para major) depois de uma versão sair. O primeiro PR atualizou o `uv` (0.12.20 → 0.12.23).
- O Dependabot só atualiza imagens escritas por extenso numa linha `FROM`. Por isso o `uv` virou um estágio
  `FROM ... AS uv`, e a troca da versão do Python (3.14 → 3.15) fica manual (a imagem vem do `ARG`).
- **Ruleset na `main`**: proíbe apagar a branch e force push, exige PR (0 aprovações, porque o GitHub não deixa
  aprovar o próprio PR) e exige os checks `Testes (Python 3.12/3.13/3.14)`, `Imagem Docker` e `Lint`.

### Fase 16 — Lint e formatação com Ruff
- **Ruff** faz lint e formatação numa ferramenta só (`[tool.ruff]` no `pyproject.toml`), com as regras `E/W`
  (estilo), `F` (pyflakes), `I` (ordem dos imports), `B` (bugbear), `UP` (sintaxe moderna), `SIM` (simplificações) e
  `S` (bandit, segurança).
- O que ele encontrou:
  - **B017 (válido):** um teste usava `pytest.raises(Exception)` e passaria até com um bug. Agora exige o `AppError`
    com status 429.
  - **S608 e S104 (falsos positivos):** SQL montado com f-string só com trechos fixos (valores sempre via `?`) e o
    `0.0.0.0` necessário no Docker. Marcados com `# noqa` e o motivo escrito do lado.
- Job **Lint** no CI: `ruff check`, `ruff format --check` e **actionlint** (verifica os workflows).

---

## 4. Ferramentas e tecnologias

| Ferramenta | Para que serve (em geral) | Como foi usada aqui | Por que foi escolhida |
|---|---|---|---|
| **Python 3.12+** | Linguagem | Toda a aplicação | Versão mínima por causa de recursos como `datetime.UTC` e `autocommit` no `sqlite3` |
| **uv** | Gerenciador de pacotes e de ambientes Python | Instalar dependências, criar o `.venv`, rodar comandos | Muito mais rápido que o pip e gera um lockfile (`uv.lock`) |
| **Flask 3** | Microframework web | Rotas, blueprints, hooks, error handlers | Pedido do projeto: a mesma API em Express e em Flask |
| **Pydantic 2** | Validação de dados com tipos Python | Schemas de body, query e params | Validação declarativa; faz o papel do Zod da versão Express |
| **PyJWT** | Gerar e validar tokens JWT | Login e `login_required` | Biblioteca padrão de JWT em Python |
| **bcrypt** | Hash de senhas | Cadastro e login | Algoritmo lento de propósito, o que dificulta força bruta |
| **SQLite (`sqlite3`)** | Banco de dados em arquivo | Usuários e tarefas | Já vem com o Python, não precisa de servidor |
| **python-dotenv** | Ler o arquivo `.env` | `main.py` | Configuração fora do código |
| **flask-cors** | Liberar acesso de outros domínios | CORS da API | Evita escrever os cabeçalhos de CORS à mão |
| **Werkzeug** | Base do Flask e servidor de desenvolvimento | Servidor com reload em dev | Já vem com o Flask |
| **waitress** | Servidor WSGI de produção | `APP_ENV=production` e Docker | Funciona no Windows |
| **pytest + pytest-cov** | Testes e cobertura | 137 testes | Padrão de mercado em Python |
| **Ruff** | Lint e formatação | `ruff check` e `ruff format` | Uma ferramenta substitui flake8, isort, black e bandit, e é muito rápida |
| **Swagger UI 5 / OpenAPI 3** | Documentação interativa de API | `/docs` e `/openapi.json` | Permite testar a API pelo navegador |
| **Docker / Compose** | Empacotar e rodar em containers | Imagem da API + volume do banco | Roda igual em qualquer máquina |
| **GitHub Actions** | CI: verificações a cada push/PR | Lint, testes em 3 versões, imagem Docker | Integrado ao GitHub, gratuito para repositório público |
| **Dependabot** | PRs automáticos de atualização | uv, actions e imagem do uv | Mantém as dependências em dia com o CI validando |
| **actionlint** | Verificar workflows do GitHub Actions | Job Lint | Pega erro de sintaxe e de shell antes do push |

### Explicando as principais

- **Flask:** um *microframework* que entrega o básico (rotas, requisição e resposta) e deixa o resto com você. Os
  **blueprints** agrupam rotas por módulo (`/auth`, `/tasks`). Os **hooks** (`before_request`, `after_request`)
  rodam código antes ou depois de toda requisição. O `g` é um "bolso" que vive durante uma única requisição.
- **Pydantic:** você descreve o formato dos dados com tipos Python (`title: str`, `status: Literal[...]`) e ele
  valida, converte e aponta os erros. `Annotated[str, StringConstraints(...)]` adiciona regras ao tipo, e os
  validadores (`BeforeValidator`/`AfterValidator`) rodam funções próprias antes ou depois da validação padrão.
- **JWT:** um token assinado com três partes (cabeçalho, payload e assinatura). O servidor não guarda sessão: ele
  confere a assinatura com o `JWT_SECRET`. O conteúdo **não é criptografado**, só assinado, então não coloque
  dados sensíveis no payload. `sub` diz quem é o usuário, `exp` quando expira e `iss` quem emitiu.
- **bcrypt:** gera um hash com *salt* aleatório. O número de rounds (`BCRYPT_ROUNDS`) controla quão lento ele é:
  cada +1 dobra o tempo.
- **uv:** substitui pip + venv + pip-tools. `uv sync` cria o ambiente igual ao `uv.lock`, e `uv run` executa os
  comandos dentro dele sem precisar ativar o `.venv`.
- **waitress vs Werkzeug:** o servidor do Werkzeug é só para desenvolvimento (reload e simplicidade). O waitress
  aguenta várias requisições ao mesmo tempo com segurança.
- **Ruff:** `ruff check` procura *erros* (imports sem uso, armadilhas, problemas de segurança) e `ruff format` cuida
  da *aparência*. `# noqa: S608` desliga uma regra só naquela linha; o certo é sempre escrever o motivo do lado.

---

## 5. Comandos usados

```bash
# Instala as dependências e cria o .venv exatamente como está no uv.lock
uv sync

# Cria o arquivo de configuração a partir do exemplo (depois edite o JWT_SECRET)
cp .env.example .env

# Gera um JWT_SECRET aleatório e seguro
uv run python -c "import secrets; print(secrets.token_hex(48))"

# Sobe a API (dev: reinicia ao salvar | APP_ENV=production: waitress)
uv run main.py

# Testes / testes com cobertura
uv run pytest
uv run pytest --cov

# Lint e formatação
uv run ruff check .
uv run ruff format .           # formata
uv run ruff format --check .   # só verifica (é o que o CI roda)

# Adiciona uma dependência (atualiza pyproject.toml e uv.lock) / só de desenvolvimento
uv add nome-do-pacote
uv add --dev nome-do-pacote

# Sobe a API em container (lê o JWT_SECRET do .env)
docker compose up --build -d

# Build com outra imagem base (usado nesta máquina por causa da imagem corrompida)
docker build --build-arg PYTHON_IMAGE=python:3.14-slim-bookworm .

# Fluxo de trabalho com a main protegida
git switch -c feat/minha-mudanca
git push -u origin feat/minha-mudanca   # depois: abrir PR, esperar o CI, fazer o merge
```

Endereços com a API rodando:
- API: http://localhost:5000
- Documentação: http://localhost:5000/docs
- Especificação: http://localhost:5000/openapi.json

---

## 6. Conceitos-chave

- **API REST:** recursos acessados por URLs (`/tasks/1`) e verbos HTTP (`GET` lê, `POST` cria, `PATCH` altera parte,
  `DELETE` remove).
- **Status HTTP:** 2xx deu certo (200, 201 criado, 204 sem conteúdo), 4xx o cliente errou (400, 401 sem login,
  403 sem permissão, 404, 409 conflito, 429 limite), 5xx o servidor errou.
- **401 vs 403:** 401 é "não sei quem você é" (token ausente ou inválido). 403 é "sei quem você é, mas isso não é
  seu" (a tarefa de outro usuário).
- **Contrato de API:** o acordo sobre o formato das requisições e respostas, incluindo os erros. É o que torna esta
  API e a versão Express intercambiáveis para um cliente.
- **Application factory:** em vez de uma variável global `app`, uma função `create_app()` monta a aplicação. Isso
  permite criar várias instâncias com configurações diferentes, como nos testes.
- **Injeção de dependência:** as peças recebem o que usam por parâmetro (`TaskService(task_repository)`) em vez de
  criar por conta própria, o que facilita trocar e testar.
- **Padrão Repository:** isola o SQL numa classe. Se um dia trocar o SQLite pelo PostgreSQL, só o repository muda.
- **Decorator:** uma função que "embrulha" outra. `@login_required` roda a checagem do token antes da rota.
- **Variáveis de ambiente / `.env`:** a configuração fica fora do código. O `.env` real **nunca** vai para o Git
  (está no `.gitignore`); o `.env.example` vai.
- **SQL injection:** quando um texto do usuário vira parte do comando SQL. A defesa é usar parâmetros (`?`).
- **Ataque de tempo (timing attack):** descobrir informação medindo quanto tempo o servidor leva para responder. É
  por isso que o login sempre roda o bcrypt, mesmo quando o e-mail não existe.
- **Claim `iss` (issuer):** campo do JWT que diz quem emitiu o token. Conferi-lo impede que um token de outro sistema
  seja aceito, mesmo com o mesmo segredo.
- **Rate limiting:** limitar quantas requisições cada IP faz numa janela de tempo. Protege contra abuso e força bruta.
- **CORS:** regra do navegador que bloqueia chamadas de um site para outro domínio, a menos que a API autorize.
- **Paginação:** devolver os resultados em páginas (`LIMIT`/`OFFSET`) com `meta.total` e `meta.totalPages`.
- **Health check:** uma rota simples que diz se a aplicação e o banco estão funcionando. O Docker usa para saber se
  o container está saudável.
- **Multi-stage build:** um Dockerfile com várias etapas. A imagem final leva só o necessário para rodar, então fica
  menor e mais segura.
- **Encerramento controlado (graceful shutdown):** ao receber Ctrl+C ou SIGTERM, terminar as requisições em
  andamento e fechar o banco antes de sair.
- **CI e matriz de versões:** verificações automáticas a cada push/PR, rodando os testes em várias versões do Python
  para garantir a versão mínima declarada.
- **Comportamento dependente de plataforma:** o mesmo código pode se comportar diferente no Windows e no Linux
  (pilha, sockets, quebras de linha). Um limite explícito no código elimina a dúvida.

---

## 7. Problemas encontrados e soluções

| Problema | Causa | Solução |
|---|---|---|
| Dois servidores rodando na **mesma porta** sem erro no Windows | `SO_REUSEADDR`, padrão do Werkzeug e do waitress, tem outro significado no Windows e permite isso | Abrir o socket com `SO_EXCLUSIVEADDRUSE` (`_bind_socket` em `main.py`) |
| Erros de protocolo saindo em **HTML ou texto puro** | O servidor HTTP responde antes de a requisição chegar ao Flask | `JsonErrorRequestHandler` (Werkzeug) e `patch_waitress_errors()` (waitress) |
| Swagger UI **sem tema escuro** | O pacote `swagger-ui-bundle` parou no Swagger UI 4.x | Arquivos do Swagger UI 5.33.1 copiados para `app/docs/swagger_ui/` |
| Script do Swagger **bloqueado** | A CSP (`script-src 'self'`) bloqueia scripts inline | Script servido como arquivo separado em `/docs/init.js` |
| Senhas longas com acento **truncadas** ou com erro | O bcrypt só usa 72 **bytes**, e acentos ocupam 2 bytes | Validar o limite em bytes no cadastro e cortar com segurança no login |
| `sub` numérico gigante no token dava 500 | O SQLite não aceita inteiros acima de 64 bits (`OverflowError`) | Validar o `sub` com a mesma regra dos IDs |
| `UnicodeEncodeError` ao logar acentos | O console do Windows nem sempre usa UTF-8 | `sys.stdout.reconfigure(encoding="utf-8")` |
| `json.loads` aceitando `NaN` | O Python aceita essas constantes por padrão, mas elas não são JSON válido | `parse_constant=_reject_constant` |
| E-mail duplicado em cadastros **simultâneos** | Corrida entre o "já existe?" e o `INSERT` | `UNIQUE` no banco + capturar `IntegrityError` e devolver 409 |
| Respostas diferentes da versão Express | Flask e Express têm comportamentos padrão diferentes (barra no final da URL, ordem de 404/405, formato de data) | `strict_slashes = False`, `login_required` por rota e `now_iso()` no formato do JavaScript |
| **Token do Flask autenticava outra pessoa no Express** | `JWT_SECRET` compartilhado entre APIs com bancos separados | Claim `iss` no token e conferência na validação (Fase 12) |
| Imagem `python:3.14-slim` corrompida no Docker local (`exec format error`, `/usr/bin/dash` com 0 bytes) | O disco C: lotou (0 GB livres) durante o build; o Docker entrou em modo somente leitura no meio da gravação das camadas | Liberar espaço; como limpar o cache não resolveu, a base virou `ARG PYTHON_IMAGE`, com `python:3.14-slim-bookworm` só no `.env` local. A solução definitiva é o "Clean / Purge data" do Docker Desktop |
| CI falhou: `Unable to resolve action astral-sh/setup-uv@v10` | Essa action não publica a tag de versão principal | Usar a versão completa `@v10.2.0` |
| Teste de JSON aninhado passava no Windows e falhava no Linux | O resultado do `json.loads` dependia do tamanho da pilha | Limite explícito de 32 níveis, checado antes do parse (Fase 14) |
| Dependabot não atualizaria o `uv` nem o Python | Ele só lê imagens escritas por extenso em linhas `FROM` | Estágio `FROM ... AS uv`; a troca de versão do Python fica manual |
| `pytest.raises(Exception)` aceitaria qualquer erro | Teste genérico demais (apontado pelo Ruff, regra B017) | Exigir `AppError` com status 429 |

---

## 8. O que aprendi

- Montar uma API Flask organizada em módulos e camadas (routes → service → repository).
- Validar entradas com Pydantic e devolver erros claros, em português e todos de uma vez.
- Centralizar o tratamento de erros num formato único, incluindo os casos fora do Flask.
- Autenticação com JWT e bcrypt, e cuidados reais de segurança (ataque de tempo, limite do bcrypt, rate limit, `iss`).
- Que "compatível" entre sistemas pode ser uma falha de segurança: tokens compartilhados exigem usuários
  compartilhados.
- Escrever SQL seguro (parâmetros, lista fechada no `ORDER BY`, escape no `LIKE`).
- Diferenças práticas entre Windows e Linux (sockets, codificação do console, pilha, servidor de produção).
- Testar uma API com pytest usando fixtures e banco em memória, e validar várias versões do Python no CI.
- Empacotar uma aplicação Python com Docker multi-stage e um usuário sem privilégios.
- Um fluxo profissional: CI, `main` protegida, PRs, Dependabot, lint e formatação automáticos.
- Comparar o mesmo projeto em duas stacks (Flask × Express) ajuda a ver o que é conceito e o que é detalhe do
  framework.

---

## 9. Próximos passos / para estudar mais

**Melhorias possíveis**
- Cobertura mínima de testes no CI (`--cov-fail-under`).
- Publicar a imagem no GitHub Container Registry e fazer o deploy.
- Trocar o SQLite por **PostgreSQL** e usar migrations (ex.: Alembic), em vez de `CREATE TABLE IF NOT EXISTS`.
- Rate limit compartilhado entre processos (ex.: Redis), já que hoje ele fica na memória de cada processo.
- Refresh token e logout (hoje o token só expira).
- Resolver a imagem corrompida no Docker local e remover o `PYTHON_IMAGE` dos `.env`.
- Frontend em Angular consumindo as duas APIs (em andamento: `task-app-angular`).

**Documentação oficial**
- Flask: https://flask.palletsprojects.com/
- Pydantic: https://docs.pydantic.dev/
- uv: https://docs.astral.sh/uv/
- PyJWT: https://pyjwt.readthedocs.io/
- pytest: https://docs.pytest.org/
- Ruff: https://docs.astral.sh/ruff/
- OpenAPI: https://spec.openapis.org/oas/latest.html
- Docker (multi-stage builds): https://docs.docker.com/build/building/multi-stage/
- GitHub Actions: https://docs.github.com/actions
- OWASP (segurança de APIs): https://owasp.org/API-Security/
