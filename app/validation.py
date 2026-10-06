from types import SimpleNamespace
from typing import ClassVar

from flask import g, request
from pydantic import BaseModel, ConfigDict, ValidationError
from pydantic.alias_generators import to_camel

from app.errors import bad_request

# Sentinela para "requisição sem corpo" (diferente de um JSON null).
MISSING = object()

# Mensagens genéricas por tipo de erro do Pydantic, usadas quando o schema
# não define uma mensagem específica para o campo.
GENERIC_MESSAGES = {
    "missing": "Campo obrigatório",
    "string_type": "Deve ser um texto",
    "int_type": "Deve ser um número inteiro",
    "int_parsing": "Deve ser um número inteiro",
    "int_from_float": "Deve ser um número inteiro",
    "literal_error": "Valor inválido, esperado: {expected}",
    "string_too_short": "Deve ter pelo menos {min_length} caracteres",
    "string_too_long": "Deve ter no máximo {max_length} caracteres",
    "greater_than_equal": "Deve ser maior ou igual a {ge}",
    "less_than_equal": "Deve ser menor ou igual a {le}",
    "model_type": "Corpo da requisição deve ser um objeto JSON",
    "model_attributes_type": "Corpo da requisição deve ser um objeto JSON",
}


class Schema(BaseModel):
    """
    Base dos schemas de entrada: campos em camelCase no JSON (snake_case no Python),
    campos desconhecidos são rejeitados.
    """

    model_config = ConfigDict(extra="forbid", alias_generator=to_camel, validate_by_name=False)

    # { "campo": { "tipo_do_erro": "mensagem" } }
    MESSAGES: ClassVar[dict[str, dict[str, str]]] = {}


def _message_for(schema, error):
    error_type = error["type"]
    if error_type == "extra_forbidden":
        return "Campo não permitido"

    loc = error["loc"]
    field = str(loc[0]) if loc else None
    template = schema.MESSAGES.get(field, {}).get(error_type) or GENERIC_MESSAGES.get(error_type)
    if template is None:
        # Erros customizados (PydanticCustomError) já trazem a mensagem final.
        return error["msg"]
    try:
        return template.format(**(error.get("ctx") or {}))
    except (KeyError, IndexError):
        return template


def format_errors(schema, exc: ValidationError, location):
    errors = exc.errors(include_url=False)

    # Se o tipo do campo está errado, as demais regras dele não fazem sentido.
    wrong_type = {e["loc"] for e in errors if e["type"].endswith("_type")}
    relevant = [e for e in errors if e["type"].endswith("_type") or e["loc"] not in wrong_type]

    return [
        {
            "location": location,
            "field": ".".join(str(part) for part in e["loc"]) or None,
            "message": _message_for(schema, e),
        }
        for e in relevant
    ]


def _query_dict():
    """Query string como dict; parâmetros repetidos viram lista (e falham na validação)."""
    args = request.args
    return {key: values[0] if len(values) == 1 else values for key, values in args.lists()}


def validate_request(*, params=None, query=None, body=None):
    """
    Valida params, query e body. Todos os problemas de todas as partes são
    devolvidos de uma vez. `params` é uma tupla (schema, dados).
    """
    result = SimpleNamespace(params=None, query=None, body=None)
    details = []

    sources = []
    if params is not None:
        schema, data = params
        sources.append(("params", schema, data))
    if query is not None:
        sources.append(("query", query, _query_dict()))
    if body is not None:
        sources.append(("body", body, g.get("body", MISSING)))

    for location, schema, data in sources:
        if location == "body" and data is MISSING:
            details.append({"location": "body", "field": None, "message": "Corpo da requisição é obrigatório"})
            continue
        try:
            setattr(result, location, schema.model_validate(data))
        except ValidationError as exc:
            details.extend(format_errors(schema, exc, location))

    if details:
        raise bad_request("VALIDATION_ERROR", "Dados da requisição inválidos", details)
    return result
