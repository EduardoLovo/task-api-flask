import time

from flask import Blueprint, jsonify

from app import logger
from app.clock import now_iso
from app.errors import service_unavailable

STARTED_AT = time.monotonic()


def create_health_blueprint(*, get_conn):
    bp = Blueprint("health", __name__)

    @bp.get("/health")
    def health():
        try:
            get_conn().execute("SELECT 1").fetchone()
        except Exception as exc:
            logger.error("Health check: banco indisponível", error=logger.serialize_error(exc))
            raise service_unavailable("DATABASE_UNAVAILABLE", "Banco de dados indisponível") from exc

        return jsonify(
            {
                "data": {
                    "status": "ok",
                    "database": "ok",
                    "uptime": round(time.monotonic() - STARTED_AT),
                    "timestamp": now_iso(),
                }
            }
        )

    return bp
