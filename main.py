"""
Ponto de entrada do servidor.

- APP_ENV=development: servidor do Werkzeug com reload automático.
- APP_ENV=production:  waitress (servidor WSGI de produção, funciona no Windows).
"""

import errno
import logging
import os
import signal
import socket
import sys
import threading
from pathlib import Path

from dotenv import load_dotenv

from app import create_app, logger
from app.config import ConfigError, load_config
from app.db import Database
from app.protocol_errors import JsonErrorRequestHandler, patch_waitress_errors

# Todas as interfaces: necessário para a API ser acessível de fora do container Docker.
HOST = "0.0.0.0"  # noqa: S104
ADDRESS_IN_USE = {errno.EADDRINUSE, getattr(errno, "WSAEADDRINUSE", None)}
ACCESS_DENIED = {errno.EACCES, getattr(errno, "WSAEACCES", None)}


def _use_utf8_output():
    # Evita UnicodeEncodeError ao logar acentos em consoles com outra codificação.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


def _install_process_hooks():
    def excepthook(exc_type, exc, tb):
        logger.error("Exceção não capturada", error=logger.serialize_error(exc))

    def thread_excepthook(args):
        logger.error(
            "Exceção não capturada em thread",
            thread=args.thread.name if args.thread else None,
            error=logger.serialize_error(args.exc_value),
        )

    sys.excepthook = excepthook
    threading.excepthook = thread_excepthook

    # SIGTERM (docker stop, gerenciadores de processo) vira um encerramento
    # controlado, igual ao Ctrl+C.
    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)


def _bind_socket(port):
    """
    Cria o socket do servidor. No Windows, SO_REUSEADDR (usado por padrão pelo
    waitress e pelo Werkzeug) permite que DOIS processos ocupem a mesma porta
    sem erro; SO_EXCLUSIVEADDRUSE faz o bind falhar se a porta já estiver em uso.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        else:
            # No Linux/macOS, SO_REUSEADDR só permite reaproveitar portas em TIME_WAIT.
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((HOST, port))
    except OSError:
        sock.close()
        raise
    return sock


def _port_error_message(exc, port):
    if exc.errno in ADDRESS_IN_USE:
        return f"Porta {port} já está em uso"
    if exc.errno in ACCESS_DENIED:
        return f"Sem permissão para usar a porta {port}"
    return "Erro ao iniciar o servidor HTTP"


def _log_started(config):
    logger.info(f"Servidor rodando em http://localhost:{config.port}", env=config.env)
    logger.info(f"Documentação em http://localhost:{config.port}/docs")


def run_development(app, config):
    from werkzeug.serving import is_running_from_reloader, run_simple

    # Os logs de cada requisição do Werkzeug ficam de fora; avisos e erros continuam.
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    if is_running_from_reloader():
        _log_started(config)
    else:
        # Checagem prévia: o Werkzeug abre o próprio socket logo em seguida.
        _bind_socket(config.port).close()

    run_simple(
        HOST,
        config.port,
        app,
        use_reloader=True,
        use_debugger=False,
        threaded=True,
        request_handler=JsonErrorRequestHandler,
    )


def run_production(app, config):
    from waitress.server import create_server

    patch_waitress_errors()
    server = create_server(app, sockets=[_bind_socket(config.port)], ident="")
    _log_started(config)
    # run() trata SystemExit/KeyboardInterrupt esperando as requisições em andamento.
    server.run()


def main():
    _use_utf8_output()
    if Path(".env").exists():
        load_dotenv(".env")

    try:
        config = load_config(os.environ)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    try:
        db = Database(config.database_path)
    except Exception as exc:
        logger.error(
            "Falha ao abrir o banco de dados",
            path=config.database_path,
            error=logger.serialize_error(exc),
        )
        return 1

    app = create_app(config, db)
    _install_process_hooks()

    exit_code = 0
    try:
        if config.is_development:
            run_development(app, config)
        else:
            run_production(app, config)
    except OSError as exc:
        if exc.errno in ADDRESS_IN_USE | ACCESS_DENIED:
            logger.error(_port_error_message(exc, config.port))
        else:
            logger.error(_port_error_message(exc, config.port), error=logger.serialize_error(exc))
        exit_code = 1
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        logger.info("Encerrando servidor...")
        db.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
