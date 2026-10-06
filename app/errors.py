class AppError(Exception):
    """Erro HTTP esperado. Tudo que chega ao error handler é convertido para este formato."""

    def __init__(self, status, code, message, details=None, headers=None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers or {}


def bad_request(code, message, details=None):
    return AppError(400, code, message, details)


def unauthorized(code, message):
    return AppError(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def forbidden(code, message):
    return AppError(403, code, message)


def not_found(code, message):
    return AppError(404, code, message)


def method_not_allowed(method, allowed):
    return AppError(
        405,
        "METHOD_NOT_ALLOWED",
        f"Método {method} não permitido para este recurso",
        details=[{"allowed": allowed}],
        headers={"Allow": ", ".join(allowed)},
    )


def conflict(code, message):
    return AppError(409, code, message)


def unsupported_media_type(code, message):
    return AppError(415, code, message)


def too_many_requests(message, retry_after_seconds):
    return AppError(429, "TOO_MANY_REQUESTS", message, headers={"Retry-After": str(retry_after_seconds)})


def service_unavailable(code, message):
    return AppError(503, code, message)
