import sqlite3
import uuid
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    email         TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title       TEXT    NOT NULL,
    description TEXT,
    status      TEXT    NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'in_progress', 'done')),
    priority    TEXT    NOT NULL DEFAULT 'medium'
                CHECK (priority IN ('low', 'medium', 'high')),
    due_date    TEXT,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id);
"""


class Database:
    """
    Fábrica de conexões SQLite. Cada requisição usa a sua própria conexão
    (sqlite3 não deve ser compartilhado entre threads sem cuidado).
    """

    def __init__(self, path: str):
        self._closed = False
        if path == ":memory:":
            # Banco em memória compartilhado entre as conexões deste objeto.
            self._target = f"file:task-api-{uuid.uuid4().hex}?mode=memory&cache=shared"
            self._uri = True
        else:
            Path(path).resolve().parent.mkdir(parents=True, exist_ok=True)
            self._target = path
            self._uri = False

        # Conexão "âncora": mantém o banco em memória vivo e cria o schema.
        self._keeper = self.connect()
        if not self._uri:
            self._keeper.execute("PRAGMA journal_mode = WAL")
        self._keeper.executescript(SCHEMA)

    @property
    def is_open(self):
        return not self._closed

    def connect(self) -> sqlite3.Connection:
        if self._closed:
            raise sqlite3.ProgrammingError("Banco de dados fechado")
        conn = sqlite3.connect(
            self._target,
            uri=self._uri,
            autocommit=True,
            check_same_thread=False,
            timeout=5,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def close(self):
        if not self._closed:
            self._closed = True
            self._keeper.close()


def is_unique_violation(exc: BaseException) -> bool:
    if not isinstance(exc, sqlite3.IntegrityError):
        return False
    return (
        getattr(exc, "sqlite_errorcode", None) == sqlite3.SQLITE_CONSTRAINT_UNIQUE
        or "UNIQUE constraint failed" in str(exc)
    )
