# Task API — Flask

API REST de gerenciamento de tarefas com autenticação JWT, feita em **Python + Flask**.
O foco é **tratamento de erros completo**: toda falha, esperada ou não, devolve uma resposta JSON no mesmo formato.

> Projeto irmão: `task-api-express`, com os mesmos endpoints, códigos de erro e mensagens em Node.js + Express.
> Cada API tem seu próprio banco de usuários, então os tokens **não** valem de uma para a outra: cada uma
> marca o emissor no token (`iss`) e recusa tokens emitidos pela outra, mesmo com o mesmo `JWT_SECRET`.

## Stack

| Item | Escolha |
|---|---|
| Runtime | Python ≥ 3.12, gerenciado com [uv](https://docs.astral.sh/uv/) |
| Framework | Flask 3 |
| Validação | Pydantic 2 (mensagens traduzidas para português) |
| Auth | JWT (HS256, PyJWT) + bcrypt |
| Banco | SQLite (`sqlite3` da biblioteca padrão) |
| Servidor | Werkzeug com reload (dev) / waitress (produção, funciona no Windows) |
| Segurança | flask-cors, cabeçalhos equivalentes ao helmet, rate limit próprio |
| Docs | OpenAPI 3 + Swagger UI 5.33.1 servido localmente (mesma versão do Express, com tema escuro) |
| Testes | pytest + pytest-cov |

## Como rodar

```bash
uv sync                # cria o .venv e instala as dependências
cp .env.example .env   # edite o JWT_SECRET
uv run main.py         # APP_ENV=development: reinicia ao salvar
```

- API: http://localhost:5000
- Documentação interativa: http://localhost:5000/docs
- Especificação: http://localhost:5000/openapi.json

Para gerar um `JWT_SECRET`:

```bash
uv run python -c "import secrets; print(secrets.token_hex(48))"
```

Com `APP_ENV=production`, o mesmo comando sobe o waitress.

```bash
uv run pytest          # roda a suíte
uv run pytest --cov    # com relatório de cobertura
```

### Com Docker

```bash
docker compose up --build -d   # usa o JWT_SECRET do .env
```

A imagem roda com o waitress, um usuário sem privilégios e um health check em `/health`. O banco fica no
volume `flask-data`. Para subir junto com a versão Express, use o repositório `task-api-compose`.

## Endpoints

| Método | Rota | Auth | Descrição |
|---|---|---|---|
| GET | `/health` | — | Status da API e do banco |
| POST | `/auth/register` | — | Cria conta e devolve token |
| POST | `/auth/login` | — | Autentica e devolve token |
| GET | `/auth/me` | ✔ | Dados do usuário logado |
| GET | `/tasks` | ✔ | Lista tarefas (filtros e paginação) |
| POST | `/tasks` | ✔ | Cria tarefa |
| GET | `/tasks/:id` | ✔ | Busca tarefa |
| PATCH | `/tasks/:id` | ✔ | Atualiza parcialmente |
| DELETE | `/tasks/:id` | ✔ | Remove tarefa |

Rotas autenticadas exigem `Authorization: Bearer <token>`.

### Tarefa

```json
{
  "id": 1,
  "title": "Estudar Flask",
  "description": null,
  "status": "pending",
  "priority": "medium",
  "dueDate": "2026-12-31",
  "createdAt": "2026-10-06T15:00:00.000Z",
  "updatedAt": "2026-10-06T15:00:00.000Z"
}
```

| Campo | Regras |
|---|---|
| `title` | obrigatório na criação, 1–120 caracteres |
| `description` | opcional, até 1000 caracteres, aceita `null` |
| `status` | `pending` (padrão), `in_progress`, `done` |
| `priority` | `low`, `medium` (padrão), `high` |
| `dueDate` | opcional, `YYYY-MM-DD` (data real), aceita `null` |

Campos fora dessa lista são rejeitados, inclusive em snake_case (`due_date`).

A senha deve ter de 8 caracteres a **72 bytes** em UTF-8, o limite do bcrypt (acentos ocupam 2 bytes).

### Query de `GET /tasks`

| Parâmetro | Padrão | Valores |
|---|---|---|
| `status` | — | `pending`, `in_progress`, `done` |
| `priority` | — | `low`, `medium`, `high` |
| `search` | — | texto buscado em título e descrição |
| `page` | `1` | inteiro ≥ 1 |
| `limit` | `10` | 1–100 |
| `sortBy` | `createdAt` | `createdAt`, `dueDate`, `priority`, `title` |
| `order` | `desc` | `asc`, `desc` |

Resposta: `{ "data": [...], "meta": { "page", "limit", "total", "totalPages" } }`.

## Formato de erro

**Toda** resposta de erro tem este formato:

```json
{
  "error": {
    "status": 400,
    "code": "VALIDATION_ERROR",
    "message": "Dados da requisição inválidos",
    "details": [
      { "location": "body", "field": "title", "message": "Título é obrigatório" }
    ],
    "requestId": "b3f1c2d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d"
  }
}
```

- `code` é estável e serve para o cliente tomar decisões; `message` é para humanos.
- `details` é sempre um array, vazio quando não há o que detalhar.
- `requestId` também vem no cabeçalho `X-Request-Id` e aparece nos logs, para facilitar o rastreio.

### Códigos

| Status | `code` | Quando |
|---|---|---|
| 400 | `VALIDATION_ERROR` | Body, query ou params inválidos (todos os problemas listados em `details`) |
| 400 | `INVALID_JSON` | JSON malformado, UTF-8 inválido, `NaN`, aninhamento excessivo, ou que não é objeto/array |
| 400 | `INVALID_BODY_ENCODING` | Corpo `gzip`/`deflate` corrompido |
| 400 | `BAD_REQUEST` | Requisição HTTP malformada |
| 400 | `REQUEST_ABORTED` | Corpo interrompido pelo cliente |
| 401 | `MISSING_TOKEN` | Sem cabeçalho `Authorization` |
| 401 | `INVALID_AUTH_HEADER` | Cabeçalho fora do formato `Bearer <token>` |
| 401 | `INVALID_TOKEN` | Token inválido, adulterado, sem expiração ou de usuário inexistente |
| 401 | `TOKEN_EXPIRED` | Token expirado |
| 401 | `INVALID_CREDENTIALS` | E-mail ou senha incorretos (mesma resposta e mesmo tempo para os dois casos) |
| 403 | `FORBIDDEN` | Tarefa pertence a outro usuário |
| 404 | `TASK_NOT_FOUND` | Tarefa não existe |
| 404 | `ROUTE_NOT_FOUND` | Rota não existe |
| 405 | `METHOD_NOT_ALLOWED` | Método não suportado (cabeçalho `Allow` informa os válidos) |
| 409 | `EMAIL_ALREADY_EXISTS` | E-mail já cadastrado |
| 413 | `PAYLOAD_TOO_LARGE` | Corpo acima de `BODY_LIMIT`, inclusive depois de descompactado |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Corpo com Content-Type diferente de `application/json` |
| 415 | `UNSUPPORTED_CHARSET` / `UNSUPPORTED_ENCODING` | Charset diferente de UTF-8, ou Content-Encoding além de `gzip`/`deflate` |
| 429 | `TOO_MANY_REQUESTS` | Rate limit excedido (cabeçalho `Retry-After`) |
| 431 | `REQUEST_HEADER_FIELDS_TOO_LARGE` | Cabeçalhos grandes demais (respondido pelo servidor HTTP) |
| 500 | `INTERNAL_ERROR` | Erro inesperado; detalhes só no log (e em `debug` quando `APP_ENV=development`) |
| 503 | `DATABASE_UNAVAILABLE` | Health check sem acesso ao banco |

A ordem de prioridade é a mesma do Express: 404 e 405 vêm antes de exigir token.

### Fora das requisições

- **Configuração inválida** (ex.: `JWT_SECRET` ausente): o processo não sobe e lista **todos** os problemas.
- **Porta ocupada ou sem permissão**: mensagem clara e saída com código 1. No Windows, o socket é aberto com
  `SO_EXCLUSIVEADDRUSE`. Sem isso, o `SO_REUSEADDR` padrão do waitress/Werkzeug deixaria dois processos
  ocuparem a mesma porta em silêncio.
- **HTTP malformado**: o Werkzeug e o waitress respondem antes do Flask; os dois foram ajustados para responder
  no formato JSON padrão em vez de HTML/texto.
- **Exceções fora das requisições** (`sys.excepthook`, `threading.excepthook`): logadas em JSON.
- **Ctrl+C / SIGTERM**: encerramento controlado; o waitress espera as requisições em andamento e o banco é fechado.

## Estrutura

```
main.py                     # sobe o servidor, sinais e erros de processo
app/
├── __init__.py             # create_app (injeção de config/db, facilita testes)
├── config.py               # leitura e validação das variáveis de ambiente
├── db.py                   # conexões SQLite + schema
├── errors.py               # AppError e atalhos (bad_request, not_found...)
├── error_handlers.py       # converte qualquer exceção no formato padrão
├── http_hooks.py           # request id, leitura do corpo (415/413/JSON), cabeçalhos
├── protocol_errors.py      # JSON também para erros do servidor HTTP
├── rate_limit.py           # limite por IP em memória
├── validation.py           # Pydantic → details em português
├── logger.py / clock.py
├── docs/                   # OpenAPI + Swagger UI (arquivos em docs/swagger_ui/)
└── modules/
    ├── auth/               # rotas, guard (login_required), service, schemas
    ├── tasks/              # rotas, service, repository, schemas
    ├── users/              # repository
    └── health/
tests/                      # auth, tasks, erros/infra
```

## Variáveis de ambiente

Veja [.env.example](.env.example). Só `JWT_SECRET` (mín. 32 caracteres) é obrigatória.
As mesmas do Express, trocando `NODE_ENV` por `APP_ENV`.
