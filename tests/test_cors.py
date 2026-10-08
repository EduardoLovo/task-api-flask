import re

import pytest

from app.config import ConfigError, load_config
from app.cors import parse_cors_origin
from tests.conftest import TEST_ENV

FRONT = "https://task-app.vercel.app"
PREVIEWS = "https://task-app-*-eduardo.vercel.app"


def preflight(client, origin):
    return client.options(
        "/tasks",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )


class TestCors:
    def test_com_asterisco_padrao_libera_qualquer_origem(self, make_app):
        app, _ = make_app()
        res = preflight(app.test_client(), "https://qualquer.site")
        assert res.headers.get("Access-Control-Allow-Origin") in ("*", "https://qualquer.site")

    @pytest.fixture
    def client(self, make_app):
        app, _ = make_app(CORS_ORIGIN=f"{FRONT}, {PREVIEWS}")
        return app.test_client()

    @pytest.mark.parametrize(
        "origin",
        [
            FRONT,
            "https://task-app-git-feat-x-eduardo.vercel.app",
            "https://task-app-a1b2c3-eduardo.vercel.app",
        ],
        ids=["origem exata", "preview que casa o curinga", "outro preview"],
    )
    def test_libera_origens_da_lista_devolvendo_a_propria_origem(self, client, origin):
        res = preflight(client, origin)
        assert res.status_code in (200, 204)
        assert res.headers.get("Access-Control-Allow-Origin") == origin
        assert set(res.headers.get("Access-Control-Expose-Headers").split(", ")) == {"X-Request-Id", "Location"}
        # A resposta muda conforme a origem: caches intermediários precisam saber disso.
        assert "Origin" in res.headers.get("Vary", "")

    @pytest.mark.parametrize(
        "origin",
        [
            "https://outro-site.com",
            "http://task-app.vercel.app",
            "https://task-app-x.atacante-eduardo.vercel.app",
            "https://task-app-x-eduardo.vercel.app.atacante.com",
        ],
        ids=[
            "domínio fora da lista",
            "origem exata com outro protocolo",
            "curinga tentando atravessar um ponto",
            "sufixo diferente",
        ],
    )
    def test_nao_libera_outras_origens(self, client, origin):
        res = preflight(client, origin)
        assert "Access-Control-Allow-Origin" not in res.headers

    def test_requisicoes_comuns_tambem_recebem_o_cabecalho(self, client):
        res = client.get("/health", headers={"Origin": FRONT})
        assert res.headers.get("Access-Control-Allow-Origin") == FRONT


class TestParseCorsOrigin:
    def test_ignora_espacos_itens_vazios_e_maiusculas(self):
        origins, problems = parse_cors_origin(" https://A.com ,, http://localhost:4200 ")
        assert problems == []
        assert [p.match("https://a.com") is not None for p in origins] == [True, False]
        assert origins[1].match("http://localhost:4200")
        # Origem exata não casa prefixos nem sufixos.
        assert not origins[0].match("https://a.com.br")
        assert not origins[0].match("https://aXcom")

    def test_converte_o_curinga_numa_expressao_que_nao_casa_pontos(self):
        (pattern,), _ = parse_cors_origin("https://app-*.vercel.app")
        assert isinstance(pattern, re.Pattern)
        assert pattern.match("https://app-abc-123.vercel.app")
        assert not pattern.match("https://app-a.b.vercel.app")
        assert not pattern.match("https://app-.vercel.app")

    @pytest.mark.parametrize(
        ("value", "message"),
        [
            ("https://app.com/", 'origem inválida "https://app.com/"'),
            ("https://app.com/front", "origem inválida"),
            ("app.com", "origem inválida"),
            ("*, https://app.com", "deve vir sozinho"),
            (" , ", "ao menos uma origem"),
        ],
        ids=["barra no final", "caminho", "sem protocolo", "asterisco junto de outras origens", "lista vazia"],
    )
    def test_recusa_valores_invalidos_ao_subir_a_api(self, value, message):
        with pytest.raises(ConfigError, match="CORS_ORIGIN") as info:
            load_config({**TEST_ENV, "CORS_ORIGIN": value})
        assert message in str(info.value)
