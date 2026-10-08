"""Leitura do CORS_ORIGIN.

Aceita "*" (qualquer origem) ou uma lista separada por vírgulas. Cada item é uma origem exata
(https://app.exemplo.com) ou tem "*" no lugar de um trecho do nome do host (https://app-*.vercel.app),
útil para URLs de preview. O "*" casa letras, números e hífens, mas nunca um ponto:
https://app-*.vercel.app não aceita https://app-x.dominio-de-outro.vercel.app.
A mesma regra vale na versão Express (src/config/cors.js).
"""

import re

ORIGIN_RE = re.compile(r"^https?://[a-z0-9*.-]+(:\d{1,5})?$")
WILDCARD = "[a-z0-9-]+"


def to_pattern(origin: str) -> re.Pattern:
    """Origem (com ou sem "*") como expressão regular ancorada.

    Mesmo as exatas viram regex: o flask-cors trata strings com "." como possíveis regex, e assim a
    comparação fica igual à do Express.
    """
    pattern = WILDCARD.join(re.escape(part) for part in origin.split("*"))
    return re.compile(rf"^{pattern}\Z")


def parse_cors_origin(value: str) -> tuple[str | tuple[re.Pattern, ...] | None, list[str]]:
    """Devolve (origens, problemas): "*" ou tupla de regex, e a lista de motivos se algo for inválido."""
    items = [item.strip().lower() for item in value.split(",") if item.strip()]

    if not items:
        return None, ['informe "*" ou ao menos uma origem']
    if "*" in items:
        if len(items) == 1:
            return "*", []
        return None, ['"*" libera qualquer origem e deve vir sozinho']

    problems = [
        f'origem inválida "{item}": use o formato https://dominio.com, sem caminho nem barra no final'
        for item in items
        if not ORIGIN_RE.fullmatch(item)
    ]
    if problems:
        return None, problems
    return tuple(to_pattern(item) for item in items), []
