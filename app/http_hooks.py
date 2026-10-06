import json
import re
import uuid
import zlib

from flask import g, request

from app.errors import AppError, bad_request, unsupported_media_type
from app.json_depth import MAX_JSON_DEPTH, exceeds_json_depth
from app.validation import MISSING

VALID_REQUEST_ID = re.compile(r"^[\w-]{1,100}$", re.ASCII)
METHODS_WITH_BODY = {"POST", "PUT", "PATCH"}
# gzip e deflate são aceitos, como no express.json(); o resto é rejeitado.
ZLIB_WBITS = {"gzip": 16 + zlib.MAX_WBITS, "deflate": zlib.MAX_WBITS}

# Equivalente aos padrões do helmet.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self';base-uri 'self';font-src 'self' https: data:;form-action 'self';"
        "frame-ancestors 'self';img-src 'self' data:;object-src 'none';script-src 'self';"
        "script-src-attr 'none';style-src 'self' https: 'unsafe-inline';upgrade-insecure-requests"
    ),
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Origin-Agent-Cluster": "?1",
    "Referrer-Policy": "no-referrer",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "X-Content-Type-Options": "nosniff",
    "X-DNS-Prefetch-Control": "off",
    "X-Download-Options": "noopen",
    "X-Frame-Options": "SAMEORIGIN",
    "X-Permitted-Cross-Domain-Policies": "none",
    "X-XSS-Protection": "0",
}

PAYLOAD_TOO_LARGE = AppError(413, "PAYLOAD_TOO_LARGE", "Corpo da requisição excede o tamanho máximo permitido")


def assign_request_id():
    """Reaproveita o X-Request-Id do cliente/proxy quando seguro, senão gera um novo."""
    incoming = request.headers.get("X-Request-Id")
    g.request_id = incoming if incoming and VALID_REQUEST_ID.fullmatch(incoming) else str(uuid.uuid4())


def _has_body():
    if request.headers.get("Transfer-Encoding"):
        return True
    return bool(request.content_length)


def _reject_constant(name):
    # json.loads aceita NaN/Infinity por padrão, mas eles não são JSON válido.
    raise ValueError(f"constante inválida: {name}")


def _decompress(raw, encoding, limit):
    decompressor = zlib.decompressobj(ZLIB_WBITS[encoding])
    try:
        # Lê no máximo limit+1 bytes descompactados: protege contra "zip bombs".
        data = decompressor.decompress(raw, limit + 1)
    except zlib.error as exc:
        raise bad_request("INVALID_BODY_ENCODING", f"Corpo não está em {encoding} válido") from exc
    if len(data) > limit:
        raise PAYLOAD_TOO_LARGE
    return data


def make_body_parser(body_limit):
    def parse_json_body():
        """Valida Content-Type/charset/encoding e interpreta o JSON. Resultado em g.body."""
        g.body = MISSING
        if not _has_body():
            return

        is_json = request.mimetype == "application/json"
        if request.method in METHODS_WITH_BODY and not is_json:
            raise unsupported_media_type("UNSUPPORTED_MEDIA_TYPE", "Content-Type deve ser application/json")
        if not is_json:
            return

        charset = request.mimetype_params.get("charset", "utf-8").lower()
        if charset not in ("utf-8", "utf8"):
            raise unsupported_media_type("UNSUPPORTED_CHARSET", "Charset não suportado, use utf-8")

        encoding = request.headers.get("Content-Encoding", "identity").strip().lower()
        if encoding not in ("identity", *ZLIB_WBITS):
            raise unsupported_media_type("UNSUPPORTED_ENCODING", "Content-Encoding não suportado")

        # Lança RequestEntityTooLarge (413) se passar de MAX_CONTENT_LENGTH.
        raw = request.get_data(cache=True)
        if encoding in ZLIB_WBITS:
            raw = _decompress(raw, encoding, body_limit)

        if exceeds_json_depth(raw):
            raise bad_request(
                "INVALID_JSON", f"JSON com aninhamento excessivo (máximo de {MAX_JSON_DEPTH} níveis)"
            )

        try:
            data = json.loads(raw.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            raise bad_request("INVALID_JSON", "JSON malformado no corpo da requisição") from exc

        # Mesmo comportamento "strict" do express.json(): só objeto ou array.
        if not isinstance(data, (dict, list)):
            raise bad_request("INVALID_JSON", "JSON malformado no corpo da requisição")
        g.body = data

    return parse_json_body


def add_response_headers(response):
    response.headers["X-Request-Id"] = g.get("request_id", "")
    for name, value in g.get("rate_limit_headers", {}).items():
        response.headers[name] = value
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response
