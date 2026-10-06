import sqlite3

from app.clock import now_iso
from app.db import is_unique_violation
from app.errors import conflict


def _to_user(row):
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "email": row["email"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class UserRepository:
    def __init__(self, get_conn):
        self._conn = get_conn

    def find_by_id(self, user_id):
        return _to_user(self._conn().execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone())

    def find_by_email(self, email):
        return _to_user(self._conn().execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone())

    def create(self, *, name, email, password_hash):
        now = now_iso()
        try:
            cursor = self._conn().execute(
                "INSERT INTO users (name, email, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (name, email, password_hash, now, now),
            )
        except sqlite3.IntegrityError as exc:
            # Cobre a corrida entre a checagem prévia e o INSERT.
            if is_unique_violation(exc):
                raise conflict("EMAIL_ALREADY_EXISTS", "Este e-mail já está cadastrado") from exc
            raise
        return self.find_by_id(cursor.lastrowid)
