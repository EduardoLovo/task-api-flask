from flask import Blueprint, Response, jsonify, send_from_directory
from swagger_ui_bundle import swagger_ui_path
from werkzeug.exceptions import NotFound

from app.docs.openapi import OPENAPI

# Só os arquivos do Swagger UI que a página usa; o resto do pacote não é exposto.
STATIC_FILES = {"swagger-ui.css", "swagger-ui-bundle.js", "favicon-32x32.png", "favicon-16x16.png"}

INDEX_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task API (Flask) - Documentação</title>
  <link rel="stylesheet" href="/docs/swagger-ui.css">
  <link rel="icon" type="image/png" href="/docs/favicon-32x32.png">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="/docs/swagger-ui-bundle.js"></script>
  <script src="/docs/init.js"></script>
</body>
</html>
"""

# Script separado (e não inline) para funcionar com a Content-Security-Policy.
INIT_JS = "window.ui = SwaggerUIBundle({ url: '/openapi.json', dom_id: '#swagger-ui' });\n"


def create_docs_blueprint():
    bp = Blueprint("docs", __name__)

    @bp.get("/openapi.json")
    def openapi_spec():
        return jsonify(OPENAPI)

    @bp.get("/docs")
    def docs_index():
        return Response(INDEX_HTML, mimetype="text/html")

    @bp.get("/docs/init.js")
    def docs_init():
        return Response(INIT_JS, mimetype="text/javascript")

    @bp.get("/docs/<filename>")
    def docs_static(filename):
        if filename not in STATIC_FILES:
            raise NotFound()
        return send_from_directory(swagger_ui_path, filename)

    return bp
