"""Logger mínimo em JSON (uma linha por evento). Silencioso durante os testes."""

import json
import os
import sys
import traceback

from app.clock import now_iso


def _write(level, message, meta):
    if os.environ.get("APP_ENV") == "test":
        return

    entry = {"level": level, "time": now_iso(), "message": message, **meta}
    stream = sys.stderr if level == "error" else sys.stdout
    print(json.dumps(entry, ensure_ascii=False, default=str), file=stream, flush=True)


def info(message, **meta):
    _write("info", message, meta)


def warn(message, **meta):
    _write("warn", message, meta)


def error(message, **meta):
    _write("error", message, meta)


def serialize_error(exc):
    if not isinstance(exc, BaseException):
        return {"value": str(exc)}
    return {
        "name": type(exc).__name__,
        "message": str(exc),
        "stack": "".join(traceback.format_exception(exc)),
    }
