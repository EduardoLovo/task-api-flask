import time

import jwt
import pytest

from app.modules.auth.service import JWT_ISSUER
from app.modules.users.repository import UserRepository
from tests.conftest import TEST_ENV, expect_error, register_user


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


def sign(*, sub, iss=JWT_ISSUER, exp="default"):
    """Assina um token com o segredo de teste. iss=None/exp=None omitem o campo."""
    payload = {"sub": sub, "iss": iss, "exp": int(time.time()) + 60 if exp == "default" else exp}
    payload = {key: value for key, value in payload.items() if value is not None}
    return jwt.encode(payload, TEST_ENV["JWT_SECRET"], "HS256")


class TestRegister:
    def test_cria_conta_e_devolve_usuario_e_token(self, client):
        res = client.post(
            "/auth/register",
            json={"name": "  Maria  ", "email": " MARIA@Example.com ", "password": "senha-segura-123"},
        )
        assert res.status_code == 201
        data = res.get_json()["data"]
        assert data["user"] == {
            "id": data["user"]["id"],
            "name": "Maria",
            "email": "maria@example.com",
            "createdAt": data["user"]["createdAt"],
        }
        assert isinstance(data["user"]["id"], int)
        assert data["tokenType"] == "Bearer"
        assert isinstance(data["accessToken"], str)
        assert "passwordHash" not in data["user"]

    def test_400_quando_faltam_campos_listando_todos(self, client):
        error = expect_error(client.post("/auth/register", json={}), 400, "VALIDATION_ERROR")
        fields = {d["field"] for d in error["details"]}
        assert {"name", "email", "password"} <= fields

    def test_400_para_email_invalido_e_senha_curta(self, client):
        res = client.post("/auth/register", json={"name": "Ana", "email": "nao-e-email", "password": "123"})
        error = expect_error(res, 400, "VALIDATION_ERROR")
        assert {"location": "body", "field": "email", "message": "E-mail inválido"} in error["details"]
        assert {
            "location": "body",
            "field": "password",
            "message": "Senha deve ter pelo menos 8 caracteres",
        } in error["details"]

    def test_400_para_senha_acima_de_72_bytes(self, client):
        res = client.post("/auth/register", json={"name": "Ana", "email": "ana@example.com", "password": "a" * 73})
        error = expect_error(res, 400, "VALIDATION_ERROR")
        assert error["details"][0]["message"] == "Senha deve ter no máximo 72 bytes"

    def test_conta_bytes_e_nao_caracteres(self, client):
        res = client.post("/auth/register", json={"name": "Ana", "email": "ana@example.com", "password": "á" * 37})
        expect_error(res, 400, "VALIDATION_ERROR")

    def test_aceita_senha_com_exatamente_72_bytes(self, client):
        res = client.post("/auth/register", json={"name": "Ana", "email": "ana@example.com", "password": "á" * 36})
        assert res.status_code == 201

    def test_400_para_tipos_errados_um_erro_por_campo(self, client):
        res = client.post("/auth/register", json={"name": 123, "email": True, "password": ["x"]})
        error = expect_error(res, 400, "VALIDATION_ERROR")
        assert error["details"] == [
            {"location": "body", "field": "name", "message": "Nome deve ser um texto"},
            {"location": "body", "field": "email", "message": "E-mail deve ser um texto"},
            {"location": "body", "field": "password", "message": "Senha deve ser um texto"},
        ]

    def test_400_para_campos_nao_permitidos(self, client):
        res = client.post(
            "/auth/register",
            json={"name": "Ana", "email": "ana@example.com", "password": "senha-segura-123", "role": "admin"},
        )
        error = expect_error(res, 400, "VALIDATION_ERROR")
        assert error["details"] == [{"location": "body", "field": "role", "message": "Campo não permitido"}]

    def test_400_quando_o_corpo_e_um_array(self, client):
        expect_error(client.post("/auth/register", json=[1, 2]), 400, "VALIDATION_ERROR")

    def test_409_para_email_ja_cadastrado_sem_diferenciar_maiusculas(self, client):
        register_user(client, email="dup@example.com")
        res = client.post(
            "/auth/register",
            json={"name": "Outro", "email": "DUP@example.com", "password": "senha-segura-123"},
        )
        expect_error(res, 409, "EMAIL_ALREADY_EXISTS")

    def test_409_mesmo_quando_dois_cadastros_passam_juntos_pela_checagem(self, db):
        conn = db.connect()
        repo = UserRepository(lambda: conn)
        data = {"name": "A", "email": "race@example.com", "password_hash": "hash"}
        repo.create(**data)
        with pytest.raises(Exception) as info:
            repo.create(**data)
        assert info.value.status == 409
        assert info.value.code == "EMAIL_ALREADY_EXISTS"
        conn.close()


class TestLogin:
    def test_autentica_com_credenciais_corretas(self, client):
        user = register_user(client)
        res = client.post("/auth/login", json={"email": user["user"]["email"], "password": user["password"]})
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["user"]["id"] == user["user"]["id"]
        assert isinstance(data["accessToken"], str)

    def test_401_para_senha_errada(self, client):
        user = register_user(client)
        res = client.post("/auth/login", json={"email": user["user"]["email"], "password": "senha-errada-000"})
        expect_error(res, 401, "INVALID_CREDENTIALS")

    def test_401_com_a_mesma_mensagem_para_email_inexistente(self, client):
        user = register_user(client)
        wrong_password = client.post(
            "/auth/login", json={"email": user["user"]["email"], "password": "senha-errada-000"}
        )
        unknown_email = client.post("/auth/login", json={"email": "ninguem@example.com", "password": "qualquer"})
        error = expect_error(unknown_email, 401, "INVALID_CREDENTIALS")
        assert error["message"] == wrong_password.get_json()["error"]["message"]

    def test_401_para_senha_acima_de_72_bytes_mesmo_com_prefixo_correto(self, client):
        password = "p" * 72
        user = register_user(client, password=password)
        res = client.post("/auth/login", json={"email": user["user"]["email"], "password": password + "extra"})
        expect_error(res, 401, "INVALID_CREDENTIALS")

    def test_401_para_senha_com_byte_nulo(self, client):
        user = register_user(client)
        res = client.post("/auth/login", json={"email": user["user"]["email"], "password": "abc\u0000def"})
        expect_error(res, 401, "INVALID_CREDENTIALS")

    def test_400_sem_corpo(self, client):
        error = expect_error(client.post("/auth/login"), 400, "VALIDATION_ERROR")
        assert error["details"] == [{"location": "body", "field": None, "message": "Corpo da requisição é obrigatório"}]


class TestMe:
    def test_devolve_o_usuario_autenticado(self, client):
        user = register_user(client)
        res = client.get("/auth/me", headers=user["auth"])
        assert res.status_code == 200
        assert res.get_json()["data"] == user["user"]

    def test_401_missing_token_com_www_authenticate(self, client):
        res = client.get("/auth/me")
        expect_error(res, 401, "MISSING_TOKEN")
        assert res.headers["WWW-Authenticate"] == "Bearer"

    @pytest.mark.parametrize("header", ["abc.def.ghi", "Basic abc", "Bearer", "Bearer a b"])
    def test_401_invalid_auth_header(self, client, header):
        expect_error(client.get("/auth/me", headers={"Authorization": header}), 401, "INVALID_AUTH_HEADER")

    def test_401_token_malformado(self, client):
        expect_error(client.get("/auth/me", headers=bearer("nao-e-um-jwt")), 401, "INVALID_TOKEN")

    def test_401_token_assinado_com_outro_segredo(self, client):
        token = jwt.encode(
            {"sub": "1", "exp": int(time.time()) + 60}, "outro-segredo-qualquer-com-32-caracteres", "HS256"
        )
        expect_error(client.get("/auth/me", headers=bearer(token)), 401, "INVALID_TOKEN")

    def test_401_algoritmo_none(self, client):
        token = jwt.encode({"sub": "1", "exp": int(time.time()) + 60}, None, algorithm="none")
        expect_error(client.get("/auth/me", headers=bearer(token)), 401, "INVALID_TOKEN")

    def test_401_token_expirado(self, client):
        user = register_user(client)
        token = sign(sub=str(user["user"]["id"]), exp=int(time.time()) - 60)
        expect_error(client.get("/auth/me", headers=bearer(token)), 401, "TOKEN_EXPIRED")

    def test_401_quando_o_usuario_do_token_nao_existe_mais(self, client):
        expect_error(client.get("/auth/me", headers=bearer(sign(sub="999999"))), 401, "INVALID_TOKEN")

    @pytest.mark.parametrize("subject", ["abc", "99999999999999999999999", "-1"])
    def test_401_para_subject_invalido(self, client, subject):
        expect_error(client.get("/auth/me", headers=bearer(sign(sub=subject))), 401, "INVALID_TOKEN")

    def test_401_token_sem_expiracao(self, client):
        expect_error(client.get("/auth/me", headers=bearer(sign(sub="1", exp=None))), 401, "INVALID_TOKEN")

    @pytest.mark.parametrize(
        "issuer", ["task-api-express", None], ids=["emitido-pela-api-express", "sem-emissor"]
    )
    def test_401_token_com_mesmo_segredo_mas_outro_emissor(self, client, issuer):
        user = register_user(client)
        token = sign(sub=str(user["user"]["id"]), iss=issuer)
        expect_error(client.get("/auth/me", headers=bearer(token)), 401, "INVALID_TOKEN")
