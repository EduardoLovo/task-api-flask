import re
from collections.abc import Mapping
from dataclasses import dataclass

from app.cors import parse_cors_origin

ENVIRONMENTS = ("development", "production", "test")
DURATION_RE = re.compile(r"^(\d+)([smhd])$")
SIZE_RE = re.compile(r"^(\d+)\s*(b|kb|mb)?$", re.IGNORECASE)
SECONDS_PER_UNIT = {"s": 1, "m": 60, "h": 3600, "d": 86400}
BYTES_PER_UNIT = {"b": 1, "kb": 1024, "mb": 1024 * 1024}


class ConfigError(Exception):
    def __init__(self, problems):
        lines = "\n".join(f"  - {name}: {message}" for name, message in problems)
        super().__init__(f"Configuração inválida:\n{lines}")
        self.problems = problems


@dataclass(frozen=True)
class RateLimitConfig:
    window_seconds: float
    max: int
    auth_max: int


@dataclass(frozen=True)
class Config:
    env: str
    port: int
    database_path: str
    jwt_secret: str
    jwt_expires_in: str
    jwt_expires_seconds: int
    bcrypt_rounds: int
    # "*" ou as origens liberadas, já como regex (veja app/cors.py).
    cors_origins: str | tuple[re.Pattern, ...]
    body_limit_bytes: int
    rate_limit: RateLimitConfig
    trust_proxy: int = 0

    @property
    def is_production(self):
        return self.env == "production"

    @property
    def is_development(self):
        return self.env == "development"


class _Reader:
    """Lê variáveis de ambiente acumulando todos os problemas, para reportá-los de uma vez."""

    def __init__(self, env):
        self.env = env
        self.problems = []

    def _raw(self, name, default):
        value = self.env.get(name)
        return default if value is None else value.strip()

    def choice(self, name, default, choices):
        value = self._raw(name, default)
        if value not in choices:
            self.problems.append((name, f"deve ser um de: {', '.join(choices)}"))
        return value

    def integer(self, name, default, minimum, maximum=None):
        value = self._raw(name, str(default))
        if not re.fullmatch(r"-?\d+", value):
            self.problems.append((name, "deve ser um número inteiro"))
            return default
        number = int(value)
        if number < minimum or (maximum is not None and number > maximum):
            limit = f"entre {minimum} e {maximum}" if maximum is not None else f"maior ou igual a {minimum}"
            self.problems.append((name, f"deve ser {limit}"))
        return number

    def text(self, name, default=None, min_length=1, missing_message=None, short_message=None):
        value = self._raw(name, default)
        if value is None:
            self.problems.append((name, missing_message or "é obrigatório"))
            return ""
        if len(value) < min_length:
            self.problems.append((name, short_message or f"deve ter pelo menos {min_length} caracteres"))
        return value

    def duration(self, name, default):
        value = self._raw(name, default)
        match = DURATION_RE.fullmatch(value)
        if not match:
            self.problems.append((name, f"{name} deve seguir o formato <número><s|m|h|d>, ex: 1h"))
            return value, 0
        return value, int(match.group(1)) * SECONDS_PER_UNIT[match.group(2)]

    def cors_origins(self, name, default):
        origins, problems = parse_cors_origin(self._raw(name, default))
        self.problems.extend((name, message) for message in problems)
        return origins

    def size(self, name, default):
        value = self._raw(name, default)
        match = SIZE_RE.fullmatch(value)
        if not match:
            self.problems.append((name, "deve ser um tamanho como 100kb, 1mb ou 512b"))
            return 0
        return int(match.group(1)) * BYTES_PER_UNIT[(match.group(2) or "b").lower()]


def load_config(env: Mapping[str, str]) -> Config:
    r = _Reader(env)

    app_env = r.choice("APP_ENV", "development", ENVIRONMENTS)
    port = r.integer("PORT", 5000, 1, 65535)
    database_path = r.text("DATABASE_PATH", "./data/database.sqlite")
    jwt_secret = r.text(
        "JWT_SECRET",
        min_length=32,
        missing_message="JWT_SECRET é obrigatório",
        short_message="JWT_SECRET deve ter pelo menos 32 caracteres",
    )
    jwt_expires_in, jwt_expires_seconds = r.duration("JWT_EXPIRES_IN", "1h")
    bcrypt_rounds = r.integer("BCRYPT_ROUNDS", 10, 4, 15)
    cors_origins = r.cors_origins("CORS_ORIGIN", "*")
    body_limit_bytes = r.size("BODY_LIMIT", "100kb")
    window_ms = r.integer("RATE_LIMIT_WINDOW_MS", 15 * 60 * 1000, 1)
    rate_max = r.integer("RATE_LIMIT_MAX", 100, 1)
    auth_max = r.integer("AUTH_RATE_LIMIT_MAX", 10, 1)
    # Quantos proxies (load balancers) ficam na frente da API. 0 = acesso direto.
    trust_proxy = r.integer("TRUST_PROXY", 0, 0, 10)

    if r.problems:
        raise ConfigError(r.problems)

    return Config(
        env=app_env,
        port=port,
        database_path=database_path,
        jwt_secret=jwt_secret,
        jwt_expires_in=jwt_expires_in,
        jwt_expires_seconds=jwt_expires_seconds,
        bcrypt_rounds=bcrypt_rounds,
        cors_origins=cors_origins,
        body_limit_bytes=body_limit_bytes,
        rate_limit=RateLimitConfig(window_seconds=window_ms / 1000, max=rate_max, auth_max=auth_max),
        trust_proxy=trust_proxy,
    )
