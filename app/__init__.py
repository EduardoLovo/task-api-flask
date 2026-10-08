from flask import Flask, g, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from app.docs.routes import create_docs_blueprint
from app.error_handlers import register_error_handlers
from app.http_hooks import (
    add_response_headers,
    assign_request_id,
    log_access,
    make_body_parser,
    start_timer,
)
from app.modules.auth.guard import make_login_required
from app.modules.auth.routes import create_auth_blueprint
from app.modules.auth.service import AuthService
from app.modules.health.routes import create_health_blueprint
from app.modules.tasks.repository import TaskRepository
from app.modules.tasks.routes import create_tasks_blueprint
from app.modules.tasks.service import TaskService
from app.modules.users.repository import UserRepository
from app.rate_limit import RateLimiter

EXPOSED_HEADERS = ["X-Request-Id", "Location", "RateLimit", "RateLimit-Policy", "Retry-After"]


def create_app(config, db):
    app = Flask(__name__)
    # Atrás de um proxy (ex.: Render), o IP real do cliente vem no X-Forwarded-For.
    # Confiar no número exato de proxies: um a mais deixaria o cliente forjar o
    # próprio IP e escapar do rate limit.
    if config.trust_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.trust_proxy)
    app.config["MAX_CONTENT_LENGTH"] = config.body_limit_bytes
    app.json.sort_keys = False
    app.json.ensure_ascii = False
    # /tasks e /tasks/ são a mesma rota (como no Express).
    app.url_map.strict_slashes = False

    # Cabeçalhos que o JavaScript do navegador pode ler numa resposta de outra origem.
    CORS(app, origins=config.cors_origins, expose_headers=EXPOSED_HEADERS)

    # Uma conexão por requisição, aberta sob demanda e fechada no fim.
    def get_conn():
        if "db_conn" not in g:
            g.db_conn = db.connect()
        return g.db_conn

    @app.teardown_appcontext
    def close_conn(_exc):
        conn = g.pop("db_conn", None)
        if conn is not None:
            conn.close()

    user_repository = UserRepository(get_conn)
    task_repository = TaskRepository(get_conn)
    auth_service = AuthService(user_repository, config)
    task_service = TaskService(task_repository)
    login_required = make_login_required(auth_service)

    global_limiter = RateLimiter(
        window_seconds=config.rate_limit.window_seconds,
        limit=config.rate_limit.max,
        message="Muitas requisições, tente novamente mais tarde",
    )
    auth_limiter = RateLimiter(
        window_seconds=config.rate_limit.window_seconds,
        limit=config.rate_limit.auth_max,
        message="Muitas tentativas de autenticação, tente novamente mais tarde",
    )

    # A ordem importa: id da requisição → rate limit → leitura do corpo.
    app.before_request(assign_request_id)
    app.before_request(start_timer)
    app.after_request(log_access)

    @app.before_request
    def apply_global_rate_limit():
        if request.method != "OPTIONS":  # preflight de CORS não conta
            global_limiter.hit()

    app.before_request(make_body_parser(config.body_limit_bytes))
    app.after_request(add_response_headers)

    app.register_blueprint(create_health_blueprint(get_conn=get_conn))
    app.register_blueprint(create_docs_blueprint())
    app.register_blueprint(
        create_auth_blueprint(auth_service=auth_service, login_required=login_required, auth_limiter=auth_limiter)
    )
    app.register_blueprint(create_tasks_blueprint(task_service=task_service, login_required=login_required))

    register_error_handlers(app, config)
    return app
