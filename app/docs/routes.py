from pathlib import Path

from flask import Blueprint, Response, jsonify, send_from_directory
from werkzeug.exceptions import NotFound

from app.docs.openapi import OPENAPI

# Swagger UI 5.33.1 (pacote npm swagger-ui-dist, licença Apache 2.0), a mesma
# versão usada no projeto Express. Fica no repositório porque o pacote Python
# equivalente parou na 4.x, que não tem tema escuro.
SWAGGER_UI_DIR = Path(__file__).parent / "swagger_ui"
SWAGGER_UI_VERSION = "5.33.1"

# Só os arquivos que a página usa são servidos.
STATIC_FILES = {
    "swagger-ui.css",
    "swagger-ui-bundle.js",
    "swagger-ui-standalone-preset.js",
    "favicon-32x32.png",
    "favicon-16x16.png",
}

INDEX_HTML = """<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Task API (Flask) - Documentação</title>
  <link rel="stylesheet" href="/docs/swagger-ui.css">
  <link rel="icon" type="image/png" href="/docs/favicon-32x32.png" sizes="32x32">
  <link rel="icon" type="image/png" href="/docs/favicon-16x16.png" sizes="16x16">
  <style>
    html { box-sizing: border-box; overflow-y: scroll; }
    *, *:before, *:after { box-sizing: inherit; }
    body { margin: 0; background: #fafafa; }
  </style>
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="/docs/swagger-ui-bundle.js"></script>
  <script src="/docs/swagger-ui-standalone-preset.js"></script>
  <script src="/docs/init.js"></script>
</body>
</html>
"""

# Script separado (e não inline) para funcionar com a Content-Security-Policy.
# O StandaloneLayout traz a barra do topo com o botão de tema claro/escuro, e
# abre no tema escuro quando o sistema operacional está em modo escuro.
INIT_JS = """window.ui = SwaggerUIBundle({
  url: '/openapi.json',
  dom_id: '#swagger-ui',
  deepLinking: true,
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIStandalonePreset],
  plugins: [SwaggerUIBundle.plugins.DownloadUrl],
  layout: 'StandaloneLayout'
});
"""


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
        return send_from_directory(SWAGGER_UI_DIR, filename)

    return bp
