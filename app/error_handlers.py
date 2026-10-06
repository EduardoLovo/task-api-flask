import uuid

from flask import g, jsonify, request
from werkzeug.exceptions import (
    ClientDisconnected,
    HTTPException,
    MethodNotAllowed,
    NotFound,
    RequestEntityTooLarge,
)

from app import logger
from app.errors import AppError, method_not_allowed, not_found

METHOD_ORDER = ["GET", "POST", "PUT", "PATCH", "DELETE"]

# Erros 4xx genéricos do Werkzeug que não têm tratamento específico.
CLIENT_ERRORS = {
    400: ("BAD_REQUEST", "Requisição inválida"),
    401: ("UNAUTHORIZED", "Não autenticado"),
    403: ("FORBIDDEN", "Acesso negado"),
    404: ("NOT_FOUND", "Recurso não encontrado"),
    408: ("REQUEST_TIMEOUT", "Tempo de requisição esgotado"),
    411: ("LENGTH_REQUIRED", "Cabeçalho Content-Length é obrigatório"),
    413: ("PAYLOAD_TOO_LARGE", "Corpo da requisição excede o tamanho máximo permitido"),
    414: ("URI_TOO_LONG", "URL longa demais"),
    415: ("UNSUPPORTED_MEDIA_TYPE", "Content-Type não suportado"),
    429: ("TOO_MANY_REQUESTS", "Muitas requisições, tente novamente mais tarde"),
    431: ("REQUEST_HEADER_FIELDS_TOO_LARGE", "Cabeçalhos da requisição grandes demais"),
}


def internal_error():
    return AppError(500, "INTERNAL_ERROR", "Erro interno do servidor")


def normalize_error(exc) -> AppError:
    """Converte qualquer exceção em AppError."""
    if isinstance(exc, AppError):
        return exc

    if isinstance(exc, MethodNotAllowed):
        allowed = [m for m in METHOD_ORDER if m in (exc.valid_methods or [])]
        return method_not_allowed(request.method, allowed)

    if isinstance(exc, NotFound):
        return not_found("ROUTE_NOT_FOUND", f"Rota {request.method} {request.path} não encontrada")

    if isinstance(exc, RequestEntityTooLarge):
        code, message = CLIENT_ERRORS[413]
        return AppError(413, code, message)

    if isinstance(exc, ClientDisconnected):
        return AppError(400, "REQUEST_ABORTED", "Requisição interrompida pelo cliente")

    if isinstance(exc, HTTPException) and exc.code is not None and 400 <= exc.code < 500:
        code, message = CLIENT_ERRORS.get(exc.code, ("CLIENT_ERROR", "Requisição inválida"))
        return AppError(exc.code, code, message)

    return internal_error()


def register_error_handlers(app, config):
    # Registrar para Exception cobre também as HTTPException do Werkzeug.
    @app.errorhandler(Exception)
    def handle_exception(exc):
        app_error = normalize_error(exc)
        request_id = g.get("request_id") or str(uuid.uuid4())

        if app_error.status >= 500:
            logger.error(
                "Erro não tratado",
                requestId=request_id,
                method=request.method,
                path=request.full_path.rstrip("?"),
                error=logger.serialize_error(exc),
            )

        body = {
            "error": {
                "status": app_error.status,
                "code": app_error.code,
                "message": app_error.message,
                "details": app_error.details,
                "requestId": request_id,
            }
        }

        # Em desenvolvimento, ajuda a depurar. Nunca em produção.
        if config.is_development and app_error.status >= 500:
            serialized = logger.serialize_error(exc)
            body["error"]["debug"] = {"message": serialized["message"], "stack": serialized["stack"]}

        response = jsonify(body)
        response.status_code = app_error.status
        response.headers.update(app_error.headers)
        return response
