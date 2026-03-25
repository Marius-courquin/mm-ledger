import uuid
from pathlib import Path

from sqlalchemy import create_engine, text, event


def create_app_db(db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{db_path}", echo=False)

    @event.listens_for(engine, "connect")
    def set_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at TEXT DEFAULT (datetime('now'))
            )
        """))
    return engine


def create_user(engine, username: str, password_hash: str, role: str = "user") -> dict:
    uid = str(uuid.uuid4())
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO users (id, username, password_hash, role) VALUES (:id, :u, :h, :r)"
        ), {"id": uid, "u": username, "h": password_hash, "r": role})
    return {"id": uid, "username": username, "role": role}


def get_user_by_username(engine, username: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE username = :u"
        ), {"u": username}).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2], "role": row[3], "created_at": row[4]}


def get_user_by_id(engine, user_id: str) -> dict | None:
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT id, username, password_hash, role, created_at FROM users WHERE id = :id"
        ), {"id": user_id}).fetchone()
    if not row:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2], "role": row[3], "created_at": row[4]}


def list_users(engine) -> list[dict]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, username, role, created_at FROM users")).fetchall()
    return [{"id": r[0], "username": r[1], "role": r[2], "created_at": r[3]} for r in rows]


def count_admins(engine) -> int:
    with engine.connect() as conn:
        return conn.execute(text("SELECT count(*) FROM users WHERE role = 'admin'")).scalar()


def delete_user(engine, user_id: str):
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": user_id})


def update_password(engine, user_id: str, password_hash: str):
    with engine.begin() as conn:
        conn.execute(text(
            "UPDATE users SET password_hash = :h WHERE id = :id"
        ), {"h": password_hash, "id": user_id})
