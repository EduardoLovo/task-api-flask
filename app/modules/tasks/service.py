import math

from app.errors import forbidden, not_found


def to_public_task(task):
    return {
        "id": task["id"],
        "title": task["title"],
        "description": task["description"],
        "status": task["status"],
        "priority": task["priority"],
        "dueDate": task["due_date"],
        "createdAt": task["created_at"],
        "updatedAt": task["updated_at"],
    }


class TaskService:
    def __init__(self, task_repository):
        self._tasks = task_repository

    def _get_owned_task(self, user_id, task_id):
        task = self._tasks.find_by_id(task_id)
        if task is None:
            raise not_found("TASK_NOT_FOUND", "Tarefa não encontrada")
        if task["user_id"] != user_id:
            raise forbidden("FORBIDDEN", "Você não tem permissão para acessar esta tarefa")
        return task

    def list(self, user_id, query):
        items, total = self._tasks.list(user_id=user_id, **query.model_dump())
        return {
            "data": [to_public_task(task) for task in items],
            "meta": {
                "page": query.page,
                "limit": query.limit,
                "total": total,
                "totalPages": math.ceil(total / query.limit),
            },
        }

    def get(self, user_id, task_id):
        return to_public_task(self._get_owned_task(user_id, task_id))

    def create(self, user_id, data):
        return to_public_task(self._tasks.create(user_id, **data.model_dump()))

    def update(self, user_id, task_id, data):
        self._get_owned_task(user_id, task_id)
        return to_public_task(self._tasks.update(task_id, data.changes()))

    def remove(self, user_id, task_id):
        self._get_owned_task(user_id, task_id)
        self._tasks.delete(task_id)
