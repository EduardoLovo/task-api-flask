import itertools
import os

import pytest

# Silencia o logger durante os testes.
os.environ["APP_ENV"] = "test"

from app import create_app  # noqa: E402
from app.config import load_config  # noqa: E402
from app.db import Database  # noqa: E402

TEST_ENV = {
    "APP_ENV": "test",
    "JWT_SECRET": "test-secret-with-at-least-32-characters!!",
    "JWT_EXPIRES_IN": "1h",
    "BCRYPT_ROUNDS": "4",
    "RATE_LIMIT_MAX": "10000",
    "AUTH_RATE_LIMIT_MAX": "10000",
}

_user_counter = itertools.count(1)


@pytest.fixture
def make_app():
    """Cria apps isolados (banco em memória próprio). Fecha tudo no final."""
    databases = []

    def factory(**env_overrides):
        config = load_config({**TEST_ENV, **env_overrides})
        db = Database(":memory:")
        databases.append(db)
        return create_app(config, db), db

    yield factory
    for db in databases:
        db.close()


@pytest.fixture
def app_and_db(make_app):
    return make_app()


@pytest.fixture
def db(app_and_db):
    return app_and_db[1]


@pytest.fixture
def client(app_and_db):
    return app_and_db[0].test_client()


def register_user(client, **overrides):
    payload = {
        "name": "Usuário Teste",
        "email": f"user{next(_user_counter)}@example.com",
        "password": "senha-segura-123",
        **overrides,
    }
    res = client.post("/auth/register", json=payload)
    assert res.status_code == 201, f"Falha ao registrar usuário de teste: {res.get_json()}"
    data = res.get_json()["data"]
    return {**data, "password": payload["password"], "auth": {"Authorization": f"Bearer {data['accessToken']}"}}


def create_task(client, auth, **overrides):
    res = client.post("/tasks", json={"title": "Tarefa", **overrides}, headers=auth)
    assert res.status_code == 201, f"Falha ao criar tarefa de teste: {res.get_json()}"
    return res.get_json()["data"]


def expect_error(res, status, code):
    """Garante que a resposta segue o formato padrão de erro."""
    assert res.status_code == status, res.get_json()
    assert res.mimetype == "application/json"
    body = res.get_json()
    assert set(body) == {"error"}
    error = body["error"]
    assert set(error) == {"status", "code", "message", "details", "requestId"}
    assert error["status"] == status
    assert error["code"] == code
    assert isinstance(error["message"], str) and error["message"]
    assert isinstance(error["details"], list)
    assert isinstance(error["requestId"], str) and error["requestId"]
    return error
