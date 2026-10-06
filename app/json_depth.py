"""Limite de aninhamento do JSON, checado nos bytes ANTES de interpretar o corpo."""

MAX_JSON_DEPTH = 32

_QUOTE, _BACKSLASH = ord('"'), ord("\\")
_OPEN = {ord("["), ord("{")}
_CLOSE = {ord("]"), ord("}")}


def exceeds_json_depth(raw: bytes, limit: int = MAX_JSON_DEPTH) -> bool:
    """
    True se o JSON abre mais de `limit` níveis de [ ou { (fora de strings).

    Sem esse limite, o resultado dependeria da plataforma: o json.loads lança
    RecursionError com pilhas menores (Windows) e aceita o corpo com pilhas
    maiores (Linux). Funciona direto nos bytes UTF-8: os caracteres procurados
    são ASCII e nunca aparecem dentro de caracteres multibyte.
    """
    depth = 0
    in_string = False
    escaped = False
    for byte in raw:
        if in_string:
            if escaped:
                escaped = False
            elif byte == _BACKSLASH:
                escaped = True
            elif byte == _QUOTE:
                in_string = False
        elif byte == _QUOTE:
            in_string = True
        elif byte in _OPEN:
            depth += 1
            if depth > limit:
                return True
        elif byte in _CLOSE:
            depth -= 1
    return False
