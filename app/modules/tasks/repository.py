from app.clock import now_iso

UPDATABLE_COLUMNS = {
    "title": "title",
    "description": "description",
    "status": "status",
    "priority": "priority",
    "due_date": "due_date",
}

ORDER_BY = {
    "createdAt": lambda d: f"created_at {d}, id {d}",
    # Tarefas sem prazo sempre ficam no final, independente da direção.
    "dueDate": lambda d: f"due_date IS NULL, due_date {d}, id {d}",
    "priority": lambda d: f"CASE priority WHEN 'low' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END {d}, id {d}",
    "title": lambda d: f"title COLLATE NOCASE {d}, id {d}",
}


def _to_task(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "due_date": row["due_date"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TaskRepository:
    def __init__(self, get_conn):
        self._conn = get_conn

    def find_by_id(self, task_id):
        return _to_task(self._conn().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    def list(self, *, user_id, status, priority, search, page, limit, sort_by, order):
        where = ["user_id = ?"]
        params = [user_id]

        if status:
            where.append("status = ?")
            params.append(status)
        if priority:
            where.append("priority = ?")
            params.append(priority)
        if search:
            where.append("(title LIKE ? ESCAPE '\\' OR description LIKE ? ESCAPE '\\')")
            pattern = f"%{_escape_like(search)}%"
            params.extend([pattern, pattern])

        where_sql = " AND ".join(where)
        # sort_by e order já foram validados contra uma lista fechada (sem injeção).
        order_sql = ORDER_BY[sort_by](order.upper())

        conn = self._conn()
        total = conn.execute(f"SELECT COUNT(*) AS total FROM tasks WHERE {where_sql}", params).fetchone()["total"]
        rows = conn.execute(
            f"SELECT * FROM tasks WHERE {where_sql} ORDER BY {order_sql} LIMIT ? OFFSET ?",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
        return [_to_task(row) for row in rows], total

    def create(self, user_id, *, title, description, status, priority, due_date):
        now = now_iso()
        cursor = self._conn().execute(
            """
            INSERT INTO tasks (user_id, title, description, status, priority, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, title, description, status, priority, due_date, now, now),
        )
        return self.find_by_id(cursor.lastrowid)

    def update(self, task_id, changes):
        sets = []
        params = []
        for field, value in changes.items():
            column = UPDATABLE_COLUMNS.get(field)
            if column is None:
                continue
            sets.append(f"{column} = ?")
            params.append(value)
        sets.append("updated_at = ?")
        params.extend([now_iso(), task_id])

        self._conn().execute(f"UPDATE tasks SET {', '.join(sets)} WHERE id = ?", params)
        return self.find_by_id(task_id)

    def delete(self, task_id):
        self._conn().execute("DELETE FROM tasks WHERE id = ?", (task_id,))
