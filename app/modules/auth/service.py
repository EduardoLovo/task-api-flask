import time

import bcrypt
import jwt

from app.errors import conflict, unauthorized
from app.modules.auth.schemas import MAX_PASSWORD_BYTES
from app.modules.tasks.schemas import ID_RE

JWT_ALGORITHM = "HS256"


def to_public_user(user):
    return {"id": user["id"], "name": user["name"], "email": user["email"], "createdAt": user["created_at"]}


class AuthService:
    def __init__(self, user_repository, config):
        self._users = user_repository
        self._config = config
        # Hash usado quando o e-mail não existe, para que o tempo de resposta do
        # login não revele se a conta existe ou não.
        self._dummy_hash = bcrypt.hashpw(b"dummy-password-for-timing", bcrypt.gensalt(config.bcrypt_rounds))

    def _issue_token(self, user):
        now = int(time.time())
        token = jwt.encode(
            {"sub": str(user["id"]), "iat": now, "exp": now + self._config.jwt_expires_seconds},
            self._config.jwt_secret,
            algorithm=JWT_ALGORITHM,
        )
        return {"accessToken": token, "tokenType": "Bearer", "expiresIn": self._config.jwt_expires_in}

    def register(self, *, name, email, password):
        if self._users.find_by_email(email):
            raise conflict("EMAIL_ALREADY_EXISTS", "Este e-mail já está cadastrado")
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(self._config.bcrypt_rounds))
        user = self._users.create(name=name, email=email, password_hash=password_hash.decode("ascii"))
        return {"user": to_public_user(user), **self._issue_token(user)}

    def login(self, *, email, password):
        user = self._users.find_by_email(email)
        password_bytes = password.encode("utf-8")
        # Senha acima do limite nunca foi cadastrada (e o bcrypt lançaria erro).
        # Compara com o hash fictício para manter o tempo de resposta.
        too_long = len(password_bytes) > MAX_PASSWORD_BYTES
        hashed = user["password_hash"].encode("ascii") if user and not too_long else self._dummy_hash
        valid = bcrypt.checkpw(password_bytes[:MAX_PASSWORD_BYTES], hashed)
        if not user or too_long or not valid:
            raise unauthorized("INVALID_CREDENTIALS", "E-mail ou senha inválidos")
        return {"user": to_public_user(user), **self._issue_token(user)}

    def authenticate(self, token):
        """Valida o token e retorna o usuário dono dele. Lança 401 em qualquer falha."""
        try:
            payload = jwt.decode(
                token,
                self._config.jwt_secret,
                algorithms=[JWT_ALGORITHM],
                options={"require": ["exp", "sub"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise unauthorized("TOKEN_EXPIRED", "Token expirado, faça login novamente") from exc
        except jwt.InvalidTokenError as exc:
            raise unauthorized("INVALID_TOKEN", "Token inválido") from exc

        subject = payload["sub"]
        user = self._users.find_by_id(int(subject)) if ID_RE.fullmatch(subject) else None
        if user is None:
            raise unauthorized("INVALID_TOKEN", "Token inválido")
        return to_public_user(user)
