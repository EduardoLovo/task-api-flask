from app.modules.tasks.schemas import PRIORITIES, SORT_FIELDS, STATUSES


def _error_response(description, status, code, message, details=None):
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/Error"},
                "example": {
                    "error": {
                        "status": status,
                        "code": code,
                        "message": message,
                        "details": details or [],
                        "requestId": "b3f1c2d4-5e6f-7a8b-9c0d-1e2f3a4b5c6d",
                    }
                },
            }
        },
    }


def _ref(name):
    return {"$ref": f"#/components/responses/{name}"}


def _json(schema):
    return {"content": {"application/json": {"schema": schema}}}


def _data_of(schema_name):
    return {"type": "object", "properties": {"data": {"$ref": f"#/components/schemas/{schema_name}"}}}


RESPONSES = {
    "ValidationError": _error_response(
        "Dados inválidos",
        400,
        "VALIDATION_ERROR",
        "Dados da requisição inválidos",
        [{"location": "body", "field": "title", "message": "Título é obrigatório"}],
    ),
    "Unauthorized": _error_response(
        "Não autenticado (MISSING_TOKEN, INVALID_AUTH_HEADER, INVALID_TOKEN, TOKEN_EXPIRED)",
        401,
        "MISSING_TOKEN",
        "Token de autenticação não informado",
    ),
    "Forbidden": _error_response(
        "A tarefa pertence a outro usuário", 403, "FORBIDDEN", "Você não tem permissão para acessar esta tarefa"
    ),
    "TaskNotFound": _error_response("Tarefa não encontrada", 404, "TASK_NOT_FOUND", "Tarefa não encontrada"),
    "PayloadTooLarge": _error_response(
        "Corpo maior que o limite", 413, "PAYLOAD_TOO_LARGE", "Corpo da requisição excede o tamanho máximo permitido"
    ),
    "UnsupportedMediaType": _error_response(
        "Content-Type diferente de application/json",
        415,
        "UNSUPPORTED_MEDIA_TYPE",
        "Content-Type deve ser application/json",
    ),
    "TooManyRequests": _error_response(
        "Limite de requisições excedido", 429, "TOO_MANY_REQUESTS", "Muitas requisições, tente novamente mais tarde"
    ),
    "InternalError": _error_response("Erro inesperado", 500, "INTERNAL_ERROR", "Erro interno do servidor"),
}

BODY_ERRORS = {"400": _ref("ValidationError"), "413": _ref("PayloadTooLarge"), "415": _ref("UnsupportedMediaType")}
COMMON_ERRORS = {"429": _ref("TooManyRequests"), "500": _ref("InternalError")}
AUTHED = {"security": [{"bearerAuth": []}]}
TASK_ID_PARAM = {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "minimum": 1}}

TASK_FIELDS = {
    "title": {"type": "string", "minLength": 1, "maxLength": 120},
    "description": {"type": "string", "maxLength": 1000, "nullable": True},
    "status": {"type": "string", "enum": list(STATUSES)},
    "priority": {"type": "string", "enum": list(PRIORITIES)},
    "dueDate": {"type": "string", "format": "date", "nullable": True},
}

OPENAPI = {
    "openapi": "3.0.3",
    "info": {
        "title": "Task API (Flask)",
        "version": "1.0.0",
        "description": "API de gerenciamento de tarefas com autenticação JWT. Todos os erros seguem o formato `Error`.",
    },
    "servers": [{"url": "/"}],
    "tags": [{"name": "Health"}, {"name": "Auth"}, {"name": "Tasks"}],
    "components": {
        "securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}},
        "responses": RESPONSES,
        "schemas": {
            "Error": {
                "type": "object",
                "required": ["error"],
                "properties": {
                    "error": {
                        "type": "object",
                        "required": ["status", "code", "message", "details", "requestId"],
                        "properties": {
                            "status": {"type": "integer"},
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "details": {"type": "array", "items": {"type": "object"}},
                            "requestId": {"type": "string"},
                        },
                    }
                },
            },
            "User": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "createdAt": {"type": "string", "format": "date-time"},
                },
            },
            "AuthResult": {
                "type": "object",
                "properties": {
                    "user": {"$ref": "#/components/schemas/User"},
                    "accessToken": {"type": "string"},
                    "tokenType": {"type": "string", "example": "Bearer"},
                    "expiresIn": {"type": "string", "example": "1h"},
                },
            },
            "Task": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    **TASK_FIELDS,
                    "createdAt": {"type": "string", "format": "date-time"},
                    "updatedAt": {"type": "string", "format": "date-time"},
                },
            },
            "CreateTask": {
                "type": "object",
                "required": ["title"],
                "additionalProperties": False,
                "properties": {
                    **TASK_FIELDS,
                    "status": {**TASK_FIELDS["status"], "default": "pending"},
                    "priority": {**TASK_FIELDS["priority"], "default": "medium"},
                },
            },
            "UpdateTask": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": False,
                "properties": TASK_FIELDS,
            },
        },
    },
    "paths": {
        "/health": {
            "get": {
                "tags": ["Health"],
                "summary": "Verifica se a API e o banco estão no ar",
                "responses": {
                    "200": {"description": "OK"},
                    "503": _error_response(
                        "Banco indisponível", 503, "DATABASE_UNAVAILABLE", "Banco de dados indisponível"
                    ),
                    **COMMON_ERRORS,
                },
            }
        },
        "/auth/register": {
            "post": {
                "tags": ["Auth"],
                "summary": "Cria uma conta e devolve um token",
                "requestBody": {
                    "required": True,
                    **_json(
                        {
                            "type": "object",
                            "required": ["name", "email", "password"],
                            "additionalProperties": False,
                            "properties": {
                                "name": {"type": "string", "minLength": 2, "maxLength": 100},
                                "email": {"type": "string", "format": "email"},
                                "password": {
                                    "type": "string",
                                    "minLength": 8,
                                    "description": "No máximo 72 bytes em UTF-8 (caracteres acentuados ocupam 2 bytes)",
                                },
                            },
                        }
                    ),
                },
                "responses": {
                    "201": {"description": "Conta criada", **_json(_data_of("AuthResult"))},
                    **BODY_ERRORS,
                    "409": _error_response(
                        "E-mail já cadastrado", 409, "EMAIL_ALREADY_EXISTS", "Este e-mail já está cadastrado"
                    ),
                    **COMMON_ERRORS,
                },
            }
        },
        "/auth/login": {
            "post": {
                "tags": ["Auth"],
                "summary": "Autentica e devolve um token",
                "requestBody": {
                    "required": True,
                    **_json(
                        {
                            "type": "object",
                            "required": ["email", "password"],
                            "additionalProperties": False,
                            "properties": {
                                "email": {"type": "string", "format": "email"},
                                "password": {"type": "string"},
                            },
                        }
                    ),
                },
                "responses": {
                    "200": {"description": "Autenticado", **_json(_data_of("AuthResult"))},
                    **BODY_ERRORS,
                    "401": _error_response(
                        "Credenciais inválidas", 401, "INVALID_CREDENTIALS", "E-mail ou senha inválidos"
                    ),
                    **COMMON_ERRORS,
                },
            }
        },
        "/auth/me": {
            "get": {
                "tags": ["Auth"],
                "summary": "Dados do usuário autenticado",
                **AUTHED,
                "responses": {
                    "200": {"description": "OK", **_json(_data_of("User"))},
                    "401": _ref("Unauthorized"),
                    **COMMON_ERRORS,
                },
            }
        },
        "/tasks": {
            "get": {
                "tags": ["Tasks"],
                "summary": "Lista as tarefas do usuário (com filtros e paginação)",
                **AUTHED,
                "parameters": [
                    {"name": "status", "in": "query", "schema": {"type": "string", "enum": list(STATUSES)}},
                    {"name": "priority", "in": "query", "schema": {"type": "string", "enum": list(PRIORITIES)}},
                    {"name": "search", "in": "query", "schema": {"type": "string", "maxLength": 100}},
                    {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}},
                    {
                        "name": "limit",
                        "in": "query",
                        "schema": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
                    },
                    {
                        "name": "sortBy",
                        "in": "query",
                        "schema": {"type": "string", "enum": list(SORT_FIELDS), "default": "createdAt"},
                    },
                    {
                        "name": "order",
                        "in": "query",
                        "schema": {"type": "string", "enum": ["asc", "desc"], "default": "desc"},
                    },
                ],
                "responses": {
                    "200": {
                        "description": "OK",
                        **_json(
                            {
                                "type": "object",
                                "properties": {
                                    "data": {"type": "array", "items": {"$ref": "#/components/schemas/Task"}},
                                    "meta": {
                                        "type": "object",
                                        "properties": {
                                            "page": {"type": "integer"},
                                            "limit": {"type": "integer"},
                                            "total": {"type": "integer"},
                                            "totalPages": {"type": "integer"},
                                        },
                                    },
                                },
                            }
                        ),
                    },
                    "400": _ref("ValidationError"),
                    "401": _ref("Unauthorized"),
                    **COMMON_ERRORS,
                },
            },
            "post": {
                "tags": ["Tasks"],
                "summary": "Cria uma tarefa",
                **AUTHED,
                "requestBody": {"required": True, **_json({"$ref": "#/components/schemas/CreateTask"})},
                "responses": {
                    "201": {"description": "Criada", **_json(_data_of("Task"))},
                    **BODY_ERRORS,
                    "401": _ref("Unauthorized"),
                    **COMMON_ERRORS,
                },
            },
        },
        "/tasks/{id}": {
            "parameters": [TASK_ID_PARAM],
            "get": {
                "tags": ["Tasks"],
                "summary": "Busca uma tarefa",
                **AUTHED,
                "responses": {
                    "200": {"description": "OK", **_json(_data_of("Task"))},
                    "400": _ref("ValidationError"),
                    "401": _ref("Unauthorized"),
                    "403": _ref("Forbidden"),
                    "404": _ref("TaskNotFound"),
                    **COMMON_ERRORS,
                },
            },
            "patch": {
                "tags": ["Tasks"],
                "summary": "Atualiza parcialmente uma tarefa",
                **AUTHED,
                "requestBody": {"required": True, **_json({"$ref": "#/components/schemas/UpdateTask"})},
                "responses": {
                    "200": {"description": "Atualizada", **_json(_data_of("Task"))},
                    **BODY_ERRORS,
                    "401": _ref("Unauthorized"),
                    "403": _ref("Forbidden"),
                    "404": _ref("TaskNotFound"),
                    **COMMON_ERRORS,
                },
            },
            "delete": {
                "tags": ["Tasks"],
                "summary": "Remove uma tarefa",
                **AUTHED,
                "responses": {
                    "204": {"description": "Removida"},
                    "400": _ref("ValidationError"),
                    "401": _ref("Unauthorized"),
                    "403": _ref("Forbidden"),
                    "404": _ref("TaskNotFound"),
                    **COMMON_ERRORS,
                },
            },
        },
    },
}
