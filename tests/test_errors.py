import gzip
import json

import pytest
from flask import Flask
from werkzeug.exceptions import BadGateway, RequestTimeout

from app.config import ConfigError, load_config
from app.error_handlers import normalize_error
from app.errors import AppError
from app.rate_limit import RateLimiter
from tests.conftest import TEST_ENV, expect_error, register_user


class TestRotasEMetodos:
    def test_404_para_rota_inexistente(self, client):
        error = expect_error(client.get("/nao-existe"), 404, "ROUTE_NOT_FOUND")
        assert error["message"] == "Rota GET /nao-existe não encontrada"

    @pytest.mark.parametrize(
        ("method", "path", "allow"),
        [
            ("put", "/tasks", "GET, POST"),
            ("delete", "/tasks", "GET, POST"),
            ("put", "/tasks/1", "GET, PATCH, DELETE"),
            ("get", "/auth/login", "POST"),
            ("post", "/health", "GET"),
        ],
    )
    def test_405_com_cabecalho_allow(self, client, method, path, allow):
        user = register_user(client)
        res = getattr(client, method)(path, headers=user["auth"])
        expect_error(res, 405, "METHOD_NOT_ALLOWED")
        assert res.headers["Allow"] == allow

    def test_404_e_405_tem_prioridade_sobre_o_token(self, client):
        expect_error(client.put("/tasks"), 405, "METHOD_NOT_ALLOWED")
        expect_error(client.get("/tasks/1/extra"), 404, "ROUTE_NOT_FOUND")

    def test_barra_no_final_e_a_mesma_rota(self, client):
        user = register_user(client)
        assert client.get("/tasks/", headers=user["auth"]).status_code == 200


class TestCorpoDaRequisicao:
    def test_400_json_malformado(self, client):
        res = client.post("/auth/login", data='{"email": "a@b.com",', content_type="application/json")
        expect_error(res, 400, "INVALID_JSON")

    @pytest.mark.parametrize("raw", ['"texto"', "42", "null", '{"a": NaN}'])
    def test_400_json_que_nao_e_objeto_nem_array_ou_invalido(self, client, raw):
        res = client.post("/auth/login", data=raw, content_type="application/json")
        expect_error(res, 400, "INVALID_JSON")

    @pytest.mark.parametrize("levels", [33, 50_000])
    def test_400_json_aninhado_demais(self, client, levels):
        # 50 mil níveis: abaixo do limite de tamanho, e o resultado não pode depender
        # da pilha da plataforma (antes dava INVALID_JSON no Windows e passava no Linux).
        raw = "[" * levels + "]" * levels
        res = client.post("/auth/login", data=raw, content_type="application/json")
        error = expect_error(res, 400, "INVALID_JSON")
        assert error["message"] == "JSON com aninhamento excessivo (máximo de 32 níveis)"

    def test_aceita_ate_32_niveis(self, client):
        raw = '{"a":' * 32 + "1" + "}" * 32
        res = client.post("/auth/login", data=raw, content_type="application/json")
        expect_error(res, 400, "VALIDATION_ERROR")  # chegou à validação: o JSON foi aceito

    def test_colchetes_e_aspas_escapadas_dentro_de_strings_nao_contam(self, client):
        password = 'x\\"' + "[{" * 40
        raw = '{"email": "ninguem@example.com", "password": "' + password + '"}'
        res = client.post("/auth/login", data=raw, content_type="application/json")
        expect_error(res, 401, "INVALID_CREDENTIALS")

    def test_400_utf8_invalido(self, client):
        res = client.post("/auth/login", data=b'{"email": "\xff"}', content_type="application/json")
        expect_error(res, 400, "INVALID_JSON")

    def test_413_corpo_maior_que_o_limite(self, client):
        res = client.post(
            "/auth/register",
            json={"name": "x" * 200 * 1024, "email": "a@b.com", "password": "12345678"},
        )
        expect_error(res, 413, "PAYLOAD_TOO_LARGE")

    def test_415_content_type_diferente_de_json(self, client):
        res = client.post("/auth/login", data="email=a@b.com", content_type="text/plain")
        expect_error(res, 415, "UNSUPPORTED_MEDIA_TYPE")

    def test_415_formulario(self, client):
        expect_error(client.post("/auth/login", data={"email": "a@b.com"}), 415, "UNSUPPORTED_MEDIA_TYPE")

    def test_415_charset_nao_suportado(self, client):
        res = client.post("/auth/login", data="{}", content_type="application/json; charset=latin1")
        expect_error(res, 415, "UNSUPPORTED_CHARSET")

    def test_415_content_encoding_nao_suportado(self, client):
        res = client.post(
            "/auth/login", data="{}", content_type="application/json", headers={"Content-Encoding": "compress"}
        )
        expect_error(res, 415, "UNSUPPORTED_ENCODING")

    def test_aceita_corpo_gzip(self, client):
        raw = gzip.compress(json.dumps({"email": "x@y.com", "password": "abc"}).encode())
        res = client.post(
            "/auth/login", data=raw, content_type="application/json", headers={"Content-Encoding": "gzip"}
        )
        expect_error(res, 401, "INVALID_CREDENTIALS")

    def test_400_gzip_corrompido(self, client):
        res = client.post(
            "/auth/login", data=b"nao-e-gzip", content_type="application/json", headers={"Content-Encoding": "gzip"}
        )
        expect_error(res, 400, "INVALID_BODY_ENCODING")

    def test_413_gzip_que_expande_alem_do_limite(self, client):
        bomb = gzip.compress(b'{"a": "' + b"x" * (5 * 1024 * 1024) + b'"}')
        res = client.post(
            "/auth/login", data=bomb, content_type="application/json", headers={"Content-Encoding": "gzip"}
        )
        expect_error(res, 413, "PAYLOAD_TOO_LARGE")

    def test_aceita_json_com_charset_utf8(self, client):
        res = client.post(
            "/auth/login",
            data=json.dumps({"email": "x@y.com", "password": "abc"}),
            content_type="application/json; charset=utf-8",
        )
        expect_error(res, 401, "INVALID_CREDENTIALS")


class TestFalhasInternas:
    def test_500_sem_vazar_detalhes_quando_o_banco_falha(self, client, db):
        user = register_user(client)
        db.close()
        res = client.get("/tasks", headers=user["auth"])
        error = expect_error(res, 500, "INTERNAL_ERROR")
        assert error["message"] == "Erro interno do servidor"
        assert "fechado" not in res.get_data(as_text=True)
        assert "sqlite" not in res.get_data(as_text=True).lower()

    def test_503_no_health_check_quando_o_banco_esta_fora(self, client, db):
        db.close()
        expect_error(client.get("/health"), 503, "DATABASE_UNAVAILABLE")

    def test_health_check_ok(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert (data["status"], data["database"]) == ("ok", "ok")

    def test_debug_apenas_em_desenvolvimento(self, make_app):
        def boom():
            raise RuntimeError("segredo interno")

        for env, has_debug in (("development", True), ("production", False)):
            app, _ = make_app(APP_ENV=env)
            app.add_url_rule("/boom", view_func=boom)
            res = app.test_client().get("/boom")
            assert res.status_code == 500
            error = res.get_json()["error"]
            assert ("debug" in error) is has_debug
            if has_debug:
                assert error["debug"]["message"] == "segredo interno"
            else:
                assert "segredo" not in res.get_data(as_text=True)


class TestRequestId:
    def test_gera_um_id_e_devolve_no_cabecalho_e_no_erro(self, client):
        res = client.get("/nao-existe")
        assert res.headers["X-Request-Id"]
        assert res.get_json()["error"]["requestId"] == res.headers["X-Request-Id"]

    def test_reaproveita_um_id_valido_do_cliente(self, client):
        res = client.get("/nao-existe", headers={"X-Request-Id": "meu-id-123"})
        assert res.get_json()["error"]["requestId"] == "meu-id-123"

    def test_ignora_um_id_invalido_do_cliente(self, client):
        res = client.get("/nao-existe", headers={"X-Request-Id": "<script>"})
        assert res.get_json()["error"]["requestId"] != "<script>"


class TestRateLimit:
    def test_429_apos_exceder_o_limite_global_com_retry_after(self, make_app):
        app, _ = make_app(RATE_LIMIT_MAX="2")
        client = app.test_client()
        client.get("/health")
        client.get("/health")
        res = client.get("/health")
        expect_error(res, 429, "TOO_MANY_REQUESTS")
        assert int(res.headers["Retry-After"]) > 0
        assert "RateLimit" in res.headers

    def test_429_com_limite_proprio_para_autenticacao(self, make_app):
        app, _ = make_app(AUTH_RATE_LIMIT_MAX="1")
        client = app.test_client()
        client.post("/auth/login", json={"email": "a@b.com", "password": "x"})
        res = client.post("/auth/login", json={"email": "a@b.com", "password": "x"})
        error = expect_error(res, 429, "TOO_MANY_REQUESTS")
        assert "autenticação" in error["message"]

    def test_janela_reinicia_apos_expirar(self):
        now = [0.0]
        limiter = RateLimiter(window_seconds=10, limit=1, message="x", clock=lambda: now[0])
        with Flask(__name__).test_request_context():
            limiter.hit("ip")
            with pytest.raises(AppError) as info:
                limiter.hit("ip")
            assert info.value.status == 429
            now[0] = 11.0
            limiter.hit("ip")  # nova janela: não lança


class TestCabecalhosEDocs:
    def test_cabecalhos_de_seguranca(self, client):
        res = client.get("/health")
        assert "X-Powered-By" not in res.headers
        assert res.headers["X-Content-Type-Options"] == "nosniff"
        assert "default-src 'self'" in res.headers["Content-Security-Policy"]

    def test_serve_a_especificacao_openapi(self, client):
        res = client.get("/openapi.json")
        assert res.status_code == 200
        assert res.get_json()["openapi"] == "3.0.3"

    def test_serve_o_swagger_ui(self, client):
        assert client.get("/docs").status_code == 200
        for filename in ("swagger-ui.css", "swagger-ui-bundle.js", "swagger-ui-standalone-preset.js", "init.js"):
            assert client.get(f"/docs/{filename}").status_code == 200, filename

    def test_swagger_ui_com_layout_que_tem_tema_escuro(self, client):
        assert "StandaloneLayout" in client.get("/docs/init.js").get_data(as_text=True)
        assert ".dark-mode .swagger-ui" in client.get("/docs/swagger-ui.css").get_data(as_text=True)

    def test_nao_expoe_outros_arquivos_do_pacote(self, client):
        expect_error(client.get("/docs/LICENSE"), 404, "ROUTE_NOT_FOUND")
        expect_error(client.get("/docs/..%2F..%2Fpyproject.toml"), 404, "ROUTE_NOT_FOUND")


class TestNormalizeError:
    def test_erro_comum_vira_500_generico(self, client):
        with client.application.test_request_context():
            assert normalize_error(RuntimeError("x")).code == "INTERNAL_ERROR"
            assert normalize_error(BadGateway()).status == 500

    def test_preserva_erros_4xx_do_werkzeug(self, client):
        with client.application.test_request_context():
            error = normalize_error(RequestTimeout())
            assert (error.status, error.code) == (408, "REQUEST_TIMEOUT")


class TestErrosDeProtocolo:
    def test_corpo_json_no_formato_padrao(self):
        from app.protocol_errors import protocol_error_body

        error = json.loads(protocol_error_body(400))["error"]
        assert (error["status"], error["code"]) == (400, "BAD_REQUEST")
        assert set(error) == {"status", "code", "message", "details", "requestId"}

    def test_waitress_responde_em_json(self):
        from waitress.utilities import BadRequest

        from app.protocol_errors import patch_waitress_errors

        patch_waitress_errors()
        status, headers, body = BadRequest("linha de requisição inválida").to_response("")
        assert status == "400 Bad Request"
        assert ("Content-Type", "application/json; charset=utf-8") in headers
        assert json.loads(body)["error"]["code"] == "BAD_REQUEST"


class TestConfiguracao:
    def test_falha_com_mensagem_clara_sem_jwt_secret_ou_curto(self):
        with pytest.raises(ConfigError, match="JWT_SECRET é obrigatório"):
            load_config({})
        with pytest.raises(ConfigError, match="pelo menos 32 caracteres"):
            load_config({"JWT_SECRET": "curto"})

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("PORT", "abc"),
            ("PORT", "70000"),
            ("JWT_EXPIRES_IN", "uma hora"),
            ("APP_ENV", "staging"),
            ("BODY_LIMIT", "muito"),
        ],
    )
    def test_rejeita_valores_invalidos(self, name, value):
        with pytest.raises(ConfigError, match=name):
            load_config({**TEST_ENV, name: value})

    def test_reporta_todos_os_problemas_de_uma_vez(self):
        with pytest.raises(ConfigError) as info:
            load_config({"PORT": "abc"})
        names = [name for name, _ in info.value.problems]
        assert names == ["PORT", "JWT_SECRET"]

    def test_converte_unidades(self):
        config = load_config({**TEST_ENV, "JWT_EXPIRES_IN": "2h", "BODY_LIMIT": "1mb"})
        assert config.jwt_expires_seconds == 7200
        assert config.body_limit_bytes == 1024 * 1024
