from flask import Blueprint, g, jsonify, request

from app.modules.tasks.schemas import CreateTaskBody, ListTasksQuery, TaskIdParams, UpdateTaskBody
from app.validation import validate_request


def create_tasks_blueprint(*, task_service, login_required):
    bp = Blueprint("tasks", __name__, url_prefix="/tasks")

    # A autenticação fica em cada view: rota inexistente (404) e método não
    # suportado (405) são respondidos antes de exigir token.

    @bp.get("")
    @login_required
    def list_tasks():
        query = validate_request(query=ListTasksQuery).query
        return jsonify(task_service.list(g.user["id"], query))

    @bp.post("")
    @login_required
    def create_task():
        body = validate_request(body=CreateTaskBody).body
        task = task_service.create(g.user["id"], body)
        response = jsonify({"data": task})
        response.status_code = 201
        response.headers["Location"] = f"{request.script_root}/tasks/{task['id']}"
        return response

    @bp.get("/<task_id>")
    @login_required
    def get_task(task_id):
        params = validate_request(params=(TaskIdParams, {"id": task_id})).params
        return jsonify({"data": task_service.get(g.user["id"], params.id)})

    @bp.patch("/<task_id>")
    @login_required
    def update_task(task_id):
        v = validate_request(params=(TaskIdParams, {"id": task_id}), body=UpdateTaskBody)
        return jsonify({"data": task_service.update(g.user["id"], v.params.id, v.body)})

    @bp.delete("/<task_id>")
    @login_required
    def delete_task(task_id):
        params = validate_request(params=(TaskIdParams, {"id": task_id})).params
        task_service.remove(g.user["id"], params.id)
        return "", 204

    return bp
