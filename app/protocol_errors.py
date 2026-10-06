"""
Respostas para erros de protocolo HTTP (requisição malformada, cabeçalhos
gigantes...), que são detectados pelo servidor antes de chegar ao Flask.
Garantem o mesmo formato JSON de erro também nesses casos.
"""

import json
import uuid

from werkzeug.serving import WSGIRequestHandler

PROTOCOL_ERRORS = {
    400: ("BAD_REQUEST", "Requisição HTTP malformada"),
    408: ("REQUEST_TIMEOUT", "Tempo de requisição esgotado"),
    413: ("PAYLOAD_TOO_LARGE", "Corpo da requisição excede o tamanho máximo permitido"),
    414: ("URI_TOO_LONG", "URL longa demais"),
    431: ("REQUEST_HEADER_FIELDS_TOO_LARGE", "Cabeçalhos da requisição grandes demais"),
    501: ("NOT_IMPLEMENTED", "Funcionalidade HTTP não suportada"),
    505: ("HTTP_VERSION_NOT_SUPPORTED", "Versão do HTTP não suportada"),
}


def protocol_error_body(status: int) -> bytes:
    code, message = PROTOCOL_ERRORS.get(
        status, ("INTERNAL_ERROR", "Erro interno do servidor") if status >= 500 else ("BAD_REQUEST", "Requisição inválida")
    )
    payload = {
        "error": {"status": status, "code": code, "message": message, "details": [], "requestId": str(uuid.uuid4())}
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class JsonErrorRequestHandler(WSGIRequestHandler):
    """Servidor de desenvolvimento (Werkzeug): troca a página HTML de erro por JSON."""

    def send_error(self, code, message=None, explain=None):
        short = self.responses.get(code, ("Error",))[0]
        body = protocol_error_body(code)

        self.close_connection = True
        self.send_response(code, message or short)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD" and code >= 200 and code not in (204, 304):
            self.wfile.write(body)


def patch_waitress_errors():
    """Servidor de produção (waitress): mesma troca, de texto puro para JSON."""
    from waitress import utilities

    def to_response(self, ident=None):
        return (
            f"{self.code} {self.reason}",
            [("Content-Type", "application/json; charset=utf-8")],
            protocol_error_body(self.code),
        )

    utilities.Error.to_response = to_response
