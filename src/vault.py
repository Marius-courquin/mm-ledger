import json
from pathlib import Path

import sqlcipher3


class Vault:
    def __init__(self, path: Path):
        self._path = path
        self._conn = None

    @property
    def status(self) -> str:
        if self._conn is not None:
            return "unlocked"
        if self._path.exists():
            return "locked"
        return "uninitialized"

    def setup(self, password: str) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlcipher3.connect(str(self._path), check_same_thread=False)
        conn.execute('PRAGMA key = "%s"' % password.replace('"', '""'))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS credentials (
                connector_id TEXT PRIMARY KEY,
                connector_type TEXT NOT NULL,
                label TEXT,
                data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )
        """)
        conn.commit()
        conn.close()

    def unlock(self, password: str) -> bool:
        try:
            conn = sqlcipher3.connect(str(self._path), check_same_thread=False)
            conn.execute('PRAGMA key = "%s"' % password.replace('"', '""'))
            conn.execute("SELECT count(*) FROM credentials")
            self._conn = conn
            return True
        except Exception:
            return False

    def lock(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def store(self, connector_id: str, connector_type: str, label: str, credentials: dict) -> None:
        if not self._conn:
            return
        self._conn.execute(
            """INSERT INTO credentials (connector_id, connector_type, label, data)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(connector_id) DO UPDATE SET
                 connector_type=excluded.connector_type,
                 label=excluded.label,
                 data=excluded.data,
                 updated_at=datetime('now')""",
            (connector_id, connector_type, label, json.dumps(credentials)),
        )
        self._conn.commit()

    def retrieve(self, connector_id: str) -> dict | None:
        if not self._conn:
            return None
        row = self._conn.execute(
            "SELECT data FROM credentials WHERE connector_id = ?", (connector_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def delete(self, connector_id: str) -> None:
        if not self._conn:
            return
        self._conn.execute("DELETE FROM credentials WHERE connector_id = ?", (connector_id,))
        self._conn.commit()

    def list_connectors(self) -> list[dict]:
        if not self._conn:
            return []
        rows = self._conn.execute(
            "SELECT connector_id, connector_type, label FROM credentials"
        ).fetchall()
        return [{"id": r[0], "type": r[1], "label": r[2]} for r in rows]

    def change_password(self, old_password: str, new_password: str) -> bool:
        if not self._conn:
            return False
        # Verify old password by trying to open a test connection
        try:
            test_conn = sqlcipher3.connect(str(self._path), check_same_thread=False)
            test_conn.execute('PRAGMA key = "%s"' % old_password.replace('"', '""'))
            test_conn.execute("SELECT count(*) FROM credentials")
            test_conn.close()
        except Exception:
            return False
        self._conn.execute('PRAGMA rekey = "%s"' % new_password.replace('"', '""'))
        return True
