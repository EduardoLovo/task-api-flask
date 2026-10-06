import re
from functools import wraps

from flask import g, request

from app.errors import unauthorized


def make_login_required(auth_service):
    def login_required(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            header = request.headers.get("Authorization")
            if not header:
                raise unauthorized("MISSING_TOKEN", "Token de autenticação não informado")

            parts = header.split()
            if len(parts) != 2 or not re.fullmatch(r"(?i)bearer", parts[0]):
                raise unauthorized(
                    "INVALID_AUTH_HEADER",
                    "Cabeçalho Authorization deve ter o formato: Bearer <token>",
                )

            g.user = auth_service.authenticate(parts[1])
            return view(*args, **kwargs)

        return wrapper

    return login_required
