import re
from datetime import date
from typing import Annotated, Literal

from pydantic import BeforeValidator, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from app.validation import Schema

STATUSES = ("pending", "in_progress", "done")
PRIORITIES = ("low", "medium", "high")
SORT_FIELDS = ("createdAt", "dueDate", "priority", "title")

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ID_RE = re.compile(r"^[1-9]\d{0,14}$")

Status = Literal["pending", "in_progress", "done"]
Priority = Literal["low", "medium", "high"]
SortField = Literal["createdAt", "dueDate", "priority", "title"]

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None


def _parse_due_date(value):
    if value is None:
        return None
    if isinstance(value, str) and DATE_RE.fullmatch(value):
        try:
            date.fromisoformat(value)  # rejeita datas impossíveis, como 2026-02-30
            return value
        except ValueError:
            pass
    raise PydanticCustomError("due_date_format", "Data de entrega deve estar no formato YYYY-MM-DD")


def _parse_id(value):
    if isinstance(value, str) and ID_RE.fullmatch(value):
        return int(value)
    raise PydanticCustomError("task_id", "ID deve ser um número inteiro positivo")


DueDate = Annotated[str | None, BeforeValidator(_parse_due_date)]

TASK_FIELD_MESSAGES = {
    "title": {
        "missing": "Título é obrigatório",
        "string_type": "Título deve ser um texto",
        "string_too_short": "Título não pode ser vazio",
        "string_too_long": "Título deve ter no máximo 120 caracteres",
    },
    "description": {
        "string_type": "Descrição deve ser um texto ou null",
        "string_too_long": "Descrição deve ter no máximo 1000 caracteres",
    },
    "status": {"literal_error": f"Status deve ser um de: {', '.join(STATUSES)}"},
    "priority": {"literal_error": f"Prioridade deve ser uma de: {', '.join(PRIORITIES)}"},
}


class CreateTaskBody(Schema):
    title: Title
    description: Description = None
    status: Status = "pending"
    priority: Priority = "medium"
    due_date: DueDate = None

    MESSAGES = TASK_FIELD_MESSAGES


class UpdateTaskBody(Schema):
    # Defaults não são validados pelo Pydantic: ausente = None (ignorado via
    # exclude_unset), mas um null explícito em title/status/priority é rejeitado.
    title: Title = None
    description: Description = None
    status: Status = None
    priority: Priority = None
    due_date: DueDate = None

    MESSAGES = TASK_FIELD_MESSAGES

    @model_validator(mode="after")
    def _at_least_one_field(self):
        if not self.model_fields_set:
            raise PydanticCustomError("empty_update", "Informe ao menos um campo para atualizar")
        return self

    def changes(self) -> dict:
        return self.model_dump(exclude_unset=True)


class ListTasksQuery(Schema):
    status: Status = None
    priority: Priority = None
    search: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] = None
    page: Annotated[int, Field(ge=1)] = 1
    limit: Annotated[int, Field(ge=1, le=100)] = 10
    sort_by: SortField = "createdAt"
    order: Literal["asc", "desc"] = "desc"

    MESSAGES = {
        "status": TASK_FIELD_MESSAGES["status"],
        "priority": TASK_FIELD_MESSAGES["priority"],
        "search": {
            "string_type": "search deve ser informado uma única vez",
            "string_too_short": "search não pode ser vazio",
            "string_too_long": "search deve ter no máximo 100 caracteres",
        },
        "page": {
            "int_type": "page deve ser um número",
            "int_parsing": "page deve ser um número inteiro",
            "greater_than_equal": "page deve ser maior ou igual a 1",
        },
        "limit": {
            "int_type": "limit deve ser um número",
            "int_parsing": "limit deve ser um número inteiro",
            "greater_than_equal": "limit deve ser maior ou igual a 1",
            "less_than_equal": "limit deve ser no máximo 100",
        },
        "sortBy": {"literal_error": f"sortBy deve ser um de: {', '.join(SORT_FIELDS)}"},
        "order": {"literal_error": "order deve ser asc ou desc"},
    }


class TaskIdParams(Schema):
    id: Annotated[int, BeforeValidator(_parse_id)]
