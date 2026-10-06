import re
from typing import Annotated

from pydantic import AfterValidator, StringConstraints
from pydantic_core import PydanticCustomError

from app.validation import Schema

# bcrypt só considera os primeiros 72 bytes da senha (acentos ocupam 2 bytes em UTF-8).
MAX_PASSWORD_BYTES = 72

# Mesmo padrão de e-mail usado pelo Zod na versão Express.
EMAIL_RE = re.compile(
    r"^(?!\.)(?!.*\.\.)([A-Za-z0-9_'+\-\.]*)[A-Za-z0-9_+-]@([A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}$"
)


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if len(value) > 254:
        raise PydanticCustomError("email_too_long", "E-mail deve ter no máximo 254 caracteres")
    if not EMAIL_RE.fullmatch(value):
        raise PydanticCustomError("email_invalid", "E-mail inválido")
    return value


def _check_password_bytes(value: str) -> str:
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise PydanticCustomError("password_too_long", f"Senha deve ter no máximo {MAX_PASSWORD_BYTES} bytes")
    return value


Email = Annotated[str, AfterValidator(_normalize_email)]

EMAIL_MESSAGES = {"missing": "E-mail é obrigatório", "string_type": "E-mail deve ser um texto"}
PASSWORD_MESSAGES = {"missing": "Senha é obrigatória", "string_type": "Senha deve ser um texto"}


class RegisterBody(Schema):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
    email: Email
    password: Annotated[str, StringConstraints(min_length=8), AfterValidator(_check_password_bytes)]

    MESSAGES = {
        "name": {
            "missing": "Nome é obrigatório",
            "string_type": "Nome deve ser um texto",
            "string_too_short": "Nome deve ter pelo menos 2 caracteres",
            "string_too_long": "Nome deve ter no máximo 100 caracteres",
        },
        "email": EMAIL_MESSAGES,
        "password": {**PASSWORD_MESSAGES, "string_too_short": "Senha deve ter pelo menos 8 caracteres"},
    }


class LoginBody(Schema):
    email: Email
    password: Annotated[str, StringConstraints(min_length=1)]

    MESSAGES = {
        "email": EMAIL_MESSAGES,
        "password": {**PASSWORD_MESSAGES, "string_too_short": "Senha é obrigatória"},
    }
