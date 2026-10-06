from flask import Blueprint, g, jsonify

from app.modules.auth.schemas import LoginBody, RegisterBody
from app.validation import validate_request


def create_auth_blueprint(*, auth_service, login_required, auth_limiter):
    bp = Blueprint("auth", __name__, url_prefix="/auth")

    @bp.post("/register")
    def register():
        auth_limiter.hit()
        body = validate_request(body=RegisterBody).body
        result = auth_service.register(**body.model_dump())
        return jsonify({"data": result}), 201

    @bp.post("/login")
    def login():
        auth_limiter.hit()
        body = validate_request(body=LoginBody).body
        return jsonify({"data": auth_service.login(**body.model_dump())})

    @bp.get("/me")
    @login_required
    def me():
        return jsonify({"data": g.user})

    return bp
