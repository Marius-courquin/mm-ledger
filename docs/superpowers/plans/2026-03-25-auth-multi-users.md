# Auth & Multi-utilisateurs — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter l'authentification multi-utilisateurs avec isolation complète des données par user.

**Architecture:** app.db global pour les users + JWT cookie HttpOnly. Chaque user a son dossier `data/users/{id}/` avec vault.db + ledger.db isolés. Workers tagués par user_id dans le ConnectorManager global.

**Tech Stack:** Python 3.12, FastAPI, bcrypt, python-jose (JWT), SQLite, SQLCipher

**Spec:** `docs/superpowers/specs/2026-03-25-auth-multi-users-design.md`

---

## File Structure

### Créer
```
src/auth.py                    # User model, JWT encode/decode, bcrypt, rate limiter
src/db/app_db.py               # app.db engine + users CRUD
src/api/auth_routes.py         # /api/auth/* (setup, login, logout, status)
src/api/admin_routes.py        # /api/admin/* (users CRUD)
src/api/middleware.py           # get_current_user dependency, deny set
tests/test_auth.py             # Unit tests auth module
tests/test_api_auth.py         # Integration tests auth routes
tests/test_api_admin.py        # Integration tests admin routes
frontend/src/pages/Login.tsx
frontend/src/pages/AdminUsers.tsx
frontend/src/hooks/useAuth.ts
```

### Modifier
```
pyproject.toml                 # +bcrypt
src/config.py                  # +APP_DB, JWT_SECRET_FILE, USERS_DIR paths
src/main.py                    # init app.db, migration, middleware
src/api/deps.py                # get_vault(uid), get_ledger(uid), cleanup_user
src/api/router.py              # +auth, admin routers
src/api/vault_routes.py        # scope par user
src/api/connectors.py          # scope par user
src/api/accounts.py            # scope par user
src/api/portfolio.py           # scope par user
src/api/snapshots.py           # scope par user
src/api/transactions.py        # scope par user
src/api/performance.py         # scope par user
src/api/events.py              # filtrer SSE par user
src/api/health.py              # scope workers par user
src/manager.py                 # stop_user_workers, get_user_live_data
src/scheduler.py               # itérer par user
frontend/src/api/client.ts     # credentials: 'same-origin'
frontend/src/hooks/useSSE.ts   # withCredentials
frontend/src/App.tsx           # routing auth
frontend/src/context/AppContext.tsx  # auth state
frontend/src/layouts/Sidebar.tsx    # user info, logout
```

---

## Task 1: Auth module + app.db

**Files:**
- Create: `src/auth.py`, `src/db/app_db.py`
- Modify: `src/config.py`, `pyproject.toml`
- Test: `tests/test_auth.py`

- [ ] **Step 1: Add bcrypt to pyproject.toml**

Add `"bcrypt"` to dependencies list.

- [ ] **Step 2: Install**

Run: `source .venv/bin/activate && pip install bcrypt`

- [ ] **Step 3: Update src/config.py**

```python
from pathlib import Path

DATA_DIR = Path("data")
APP_DB = DATA_DIR / "app.db"
JWT_SECRET_FILE = DATA_DIR / ".jwt_secret"
USERS_DIR = DATA_DIR / "users"
LEDGER_DB = DATA_DIR / "ledger.db"   # legacy, for migration
VAULT_DB = DATA_DIR / "vault.db"     # legacy, for migration
API_HOST = "0.0.0.0"
API_PORT = 8000
```

- [ ] **Step 4: Write tests/test_auth.py**

```python
import tempfile
from pathlib import Path
from src.auth import hash_password, verify_password, create_jwt, decode_jwt, LoginRateLimiter
from src.db.app_db import create_app_db, create_user, get_user_by_username, list_users, delete_user


def test_password_hash_and_verify():
    h = hash_password("mypassword")
    assert verify_password("mypassword", h)
    assert not verify_password("wrong", h)


def test_jwt_roundtrip():
    secret = "testsecret123"
    token = create_jwt({"user_id": "abc", "username": "marius", "role": "admin"}, secret, expires_hours=1)
    payload = decode_jwt(token, secret)
    assert payload["user_id"] == "abc"
    assert payload["username"] == "marius"
    assert payload["role"] == "admin"


def test_jwt_expired():
    secret = "testsecret123"
    token = create_jwt({"user_id": "abc", "username": "m", "role": "admin"}, secret, expires_hours=-1)
    assert decode_jwt(token, secret) is None


def test_rate_limiter():
    rl = LoginRateLimiter(max_attempts=3, window_seconds=60)
    assert rl.is_allowed("marius")
    rl.record_failure("marius")
    rl.record_failure("marius")
    rl.record_failure("marius")
    assert not rl.is_allowed("marius")
    rl.record_success("marius")
    assert rl.is_allowed("marius")


def test_app_db_crud():
    with tempfile.TemporaryDirectory() as tmp:
        engine = create_app_db(Path(tmp) / "app.db")
        user = create_user(engine, "marius", hash_password("pass"), "admin")
        assert user["username"] == "marius"
        assert user["role"] == "admin"

        found = get_user_by_username(engine, "marius")
        assert found is not None
        assert found["username"] == "marius"

        users = list_users(engine)
        assert len(users) == 1

        delete_user(engine, user["id"])
        assert get_user_by_username(engine, "marius") is None
```

- [ ] **Step 5: Write src/auth.py**

```python
import time
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
from jose import jwt, JWTError


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(12)).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_jwt(payload: dict, secret: str, expires_hours: int = 24) -> str:
    exp = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
    return jwt.encode({**payload, "exp": exp}, secret, algorithm="HS256")


def decode_jwt(token: str, secret: str) -> dict | None:
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except JWTError:
        return None


def get_or_create_jwt_secret(path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text().strip()
    secret = secrets.token_urlsafe(48)
    path.write_text(secret)
    path.chmod(0o600)
    return secret


class LoginRateLimiter:
    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        self._max = max_attempts
        self._window = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def is_allowed(self, username: str) -> bool:
        now = time.time()
        attempts = self._attempts.get(username, [])
        attempts = [t for t in attempts if now - t < self._window]
        self._attempts[username] = attempts
        return len(attempts) < self._max

    def record_failure(self, username: str):
        self._attempts.setdefault(username, []).append(time.time())

    def record_success(self, username: str):
        self._attempts.pop(username, None)
```

- [ ] **Step 6: Write src/db/app_db.py**

```python
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
```

- [ ] **Step 7: Run tests**

Run: `python3 -m pytest tests/test_auth.py -v`
Expected: 5 PASSED

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml src/config.py src/auth.py src/db/app_db.py tests/test_auth.py
git commit -m "feat: auth module (bcrypt, JWT, rate limiter) + app.db users CRUD"
```

---

## Task 2: Auth API routes

**Files:**
- Create: `src/api/auth_routes.py`, `src/api/middleware.py`
- Modify: `src/api/deps.py`, `src/api/router.py`, `src/main.py`
- Test: `tests/test_api_auth.py`

- [ ] **Step 1: Write src/api/middleware.py**

```python
from fastapi import Request, HTTPException

from src.auth import decode_jwt

_denied_users: set[str] = set()
_jwt_secret: str = ""


def set_jwt_secret(secret: str):
    global _jwt_secret
    _jwt_secret = secret


def deny_user(user_id: str):
    _denied_users.add(user_id)


class AuthUser:
    def __init__(self, id: str, username: str, role: str):
        self.id = id
        self.username = username
        self.role = role


def get_current_user(request: Request) -> AuthUser:
    token = request.cookies.get("mm_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    payload = decode_jwt(token, _jwt_secret)
    if not payload:
        raise HTTPException(401, "Session expirée")
    uid = payload.get("user_id")
    if uid in _denied_users:
        raise HTTPException(401, "Compte supprimé")
    return AuthUser(id=uid, username=payload["username"], role=payload["role"])


def require_admin(request: Request) -> AuthUser:
    user = get_current_user(request)
    if user.role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user
```

- [ ] **Step 2: Write src/api/auth_routes.py**

```python
from fastapi import APIRouter, HTTPException, Response, Request

from src.api import deps
from src.auth import hash_password, verify_password, create_jwt, get_or_create_jwt_secret, LoginRateLimiter
from src.api.middleware import set_jwt_secret, get_current_user, AuthUser
from src.db.app_db import create_user, get_user_by_username, count_admins
from src.config import JWT_SECRET_FILE

router = APIRouter(prefix="/api/auth", tags=["auth"])
_rate_limiter = LoginRateLimiter()


@router.get("/status")
def auth_status(request: Request):
    if not deps.app_db:
        return {"state": "no_admin"}
    admins = count_admins(deps.app_db)
    if admins == 0:
        return {"state": "no_admin"}
    # Check cookie
    token = request.cookies.get("mm_session")
    if token:
        from src.auth import decode_jwt
        payload = decode_jwt(token, deps.jwt_secret)
        if payload:
            return {
                "state": "logged_in",
                "user": {"id": payload["user_id"], "username": payload["username"], "role": payload["role"]},
            }
    return {"state": "logged_out"}


@router.post("/setup", status_code=201)
def auth_setup(request_body: dict, response: Response):
    username = request_body.get("username", "").strip()
    password = request_body.get("password", "")
    if len(username) < 3:
        raise HTTPException(400, "Nom d'utilisateur: 3 caractères minimum")
    if len(password) < 8:
        raise HTTPException(400, "Mot de passe: 8 caractères minimum")
    if count_admins(deps.app_db) > 0:
        raise HTTPException(409, "Un administrateur existe déjà")

    # Generate JWT secret on first setup
    deps.jwt_secret = get_or_create_jwt_secret(JWT_SECRET_FILE)
    set_jwt_secret(deps.jwt_secret)

    user = create_user(deps.app_db, username, hash_password(password), "admin")
    token = create_jwt({"user_id": user["id"], "username": user["username"], "role": "admin"}, deps.jwt_secret)
    response.set_cookie("mm_session", token, httponly=True, samesite="lax", max_age=86400)
    return {"status": "created", "user": {"id": user["id"], "username": user["username"], "role": "admin"}}


@router.post("/login")
def auth_login(request_body: dict, response: Response):
    username = request_body.get("username", "").strip()
    password = request_body.get("password", "")

    if not _rate_limiter.is_allowed(username):
        raise HTTPException(429, "Trop de tentatives. Réessayez dans quelques minutes.")

    user = get_user_by_username(deps.app_db, username)
    if not user or not verify_password(password, user["password_hash"]):
        _rate_limiter.record_failure(username)
        raise HTTPException(401, "Identifiants incorrects")

    _rate_limiter.record_success(username)
    token = create_jwt({"user_id": user["id"], "username": user["username"], "role": user["role"]}, deps.jwt_secret)
    response.set_cookie("mm_session", token, httponly=True, samesite="lax", max_age=86400)
    return {"status": "ok", "user": {"id": user["id"], "username": user["username"], "role": user["role"]}}


@router.post("/logout")
def auth_logout(request: Request, response: Response):
    try:
        user = get_current_user(request)
        deps.manager.stop_user_workers(user.id)
        deps.cleanup_user(user.id)
    except Exception:
        pass
    response.delete_cookie("mm_session")
    return {"status": "logged_out"}
```

- [ ] **Step 3: Update src/api/deps.py**

```python
from pathlib import Path
from src.vault import Vault
from src.manager import ConnectorManager
from src.db.engine import create_engine_and_tables
from src.config import USERS_DIR

app_db = None
jwt_secret: str = ""
manager: ConnectorManager | None = None

_user_vaults: dict[str, Vault] = {}
_user_engines: dict[str, object] = {}


def get_vault(user_id: str) -> Vault:
    if user_id not in _user_vaults:
        path = USERS_DIR / user_id / "vault.db"
        _user_vaults[user_id] = Vault(path)
    return _user_vaults[user_id]


def get_ledger(user_id: str):
    if user_id not in _user_engines:
        path = USERS_DIR / user_id / "ledger.db"
        _user_engines[user_id] = create_engine_and_tables(path)
    return _user_engines[user_id]


def cleanup_user(user_id: str):
    if user_id in _user_vaults:
        _user_vaults[user_id].lock()
        del _user_vaults[user_id]
    if user_id in _user_engines:
        _user_engines[user_id].dispose()
        del _user_engines[user_id]
```

- [ ] **Step 4: Update src/main.py**

Update lifespan to init app.db, JWT secret, and run migration. Add auth routes to router. Keep connector registrations.

- [ ] **Step 5: Update src/api/router.py**

Add auth_routes and admin_routes to the api_router.

- [ ] **Step 6: Write tests/test_api_auth.py**

```python
def test_auth_status_no_admin(client):
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "no_admin"


def test_auth_setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    assert r.status_code == 201
    assert r.json()["user"]["role"] == "admin"
    assert "mm_session" in r.cookies


def test_auth_setup_duplicate(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/setup", json={"username": "admin2", "password": "password123"})
    assert r.status_code == 409


def test_auth_login(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    client.post("/api/auth/logout")
    r = client.post("/api/auth/login", json={"username": "admin", "password": "password123"})
    assert r.status_code == 200
    assert "mm_session" in r.cookies


def test_auth_login_wrong_password(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/login", json={"username": "admin", "password": "wrong"})
    assert r.status_code == 401


def test_auth_status_logged_in(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "logged_in"
    assert r.json()["user"]["username"] == "admin"


def test_auth_logout(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})
    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    r = client.get("/api/auth/status")
    assert r.json()["state"] == "logged_out"


def test_protected_route_without_login(client):
    r = client.get("/api/connectors")
    assert r.status_code == 401


def test_password_too_short(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "short"})
    assert r.status_code == 400
```

- [ ] **Step 7: Update conftest.py**

The `client` fixture must now initialize `app_db` and `jwt_secret`. Update `create_app` to accept `data_dir` which drives both app.db and user dirs.

- [ ] **Step 8: Run tests**

Run: `python3 -m pytest tests/test_api_auth.py -v`
Expected: 9 PASSED

- [ ] **Step 9: Commit**

```bash
git add src/api/auth_routes.py src/api/middleware.py src/api/deps.py src/api/router.py src/main.py tests/test_api_auth.py tests/conftest.py
git commit -m "feat: auth routes (setup, login, logout, status) + JWT middleware"
```

---

## Task 3: Admin routes

**Files:**
- Create: `src/api/admin_routes.py`, `tests/test_api_admin.py`
- Modify: `src/api/router.py`

- [ ] **Step 1: Write src/api/admin_routes.py**

```python
import shutil
from fastapi import APIRouter, HTTPException, Depends

from src.api import deps
from src.api.middleware import require_admin, AuthUser, deny_user
from src.auth import hash_password
from src.db.app_db import create_user, list_users, delete_user, get_user_by_username, count_admins, get_user_by_id, update_password
from src.config import USERS_DIR

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users")
def admin_list_users(user: AuthUser = Depends(require_admin)):
    return list_users(deps.app_db)


@router.post("/users", status_code=201)
def admin_create_user(body: dict, user: AuthUser = Depends(require_admin)):
    username = body.get("username", "").strip()
    password = body.get("password", "")
    role = body.get("role", "user")
    if len(username) < 3:
        raise HTTPException(400, "Nom d'utilisateur: 3 caractères minimum")
    if len(password) < 8:
        raise HTTPException(400, "Mot de passe: 8 caractères minimum")
    if role not in ("admin", "user"):
        raise HTTPException(400, "Rôle invalide")
    if get_user_by_username(deps.app_db, username):
        raise HTTPException(409, "Ce nom d'utilisateur est déjà pris")
    new_user = create_user(deps.app_db, username, hash_password(password), role)
    return new_user


@router.put("/users/{user_id}")
def admin_update_user(user_id: str, body: dict, user: AuthUser = Depends(require_admin)):
    target = get_user_by_id(deps.app_db, user_id)
    if not target:
        raise HTTPException(404, "Utilisateur introuvable")
    password = body.get("password", "")
    if password:
        if len(password) < 8:
            raise HTTPException(400, "Mot de passe: 8 caractères minimum")
        update_password(deps.app_db, user_id, hash_password(password))
    return {"status": "updated"}


@router.delete("/users/{user_id}", status_code=204)
def admin_delete_user(user_id: str, user: AuthUser = Depends(require_admin)):
    target = get_user_by_id(deps.app_db, user_id)
    if not target:
        raise HTTPException(404, "Utilisateur introuvable")
    if target["role"] == "admin" and count_admins(deps.app_db) <= 1:
        raise HTTPException(403, "Impossible de supprimer le dernier administrateur")
    # Cleanup
    deps.manager.stop_user_workers(user_id)
    deps.cleanup_user(user_id)
    deny_user(user_id)
    # Delete data
    user_dir = USERS_DIR / user_id
    if user_dir.exists():
        shutil.rmtree(user_dir)
    delete_user(deps.app_db, user_id)
```

- [ ] **Step 2: Write tests/test_api_admin.py**

```python
def _setup_admin(client):
    client.post("/api/auth/setup", json={"username": "admin", "password": "password123"})


def test_admin_list_users(client):
    _setup_admin(client)
    r = client.get("/api/admin/users")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_admin_create_user(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123", "role": "user"})
    assert r.status_code == 201
    assert r.json()["username"] == "magni"
    r = client.get("/api/admin/users")
    assert len(r.json()) == 2


def test_admin_create_duplicate(client):
    _setup_admin(client)
    client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    assert r.status_code == 409


def test_admin_delete_user(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    uid = r.json()["id"]
    r = client.delete(f"/api/admin/users/{uid}")
    assert r.status_code == 204


def test_admin_cannot_delete_last_admin(client):
    _setup_admin(client)
    r = client.get("/api/admin/users")
    admin_id = r.json()[0]["id"]
    r = client.delete(f"/api/admin/users/{admin_id}")
    assert r.status_code == 403


def test_admin_reset_password(client):
    _setup_admin(client)
    r = client.post("/api/admin/users", json={"username": "magni", "password": "password123"})
    uid = r.json()["id"]
    r = client.put(f"/api/admin/users/{uid}", json={"password": "newpassword123"})
    assert r.status_code == 200


def test_non_admin_cannot_access(client):
    _setup_admin(client)
    client.post("/api/admin/users", json={"username": "magni", "password": "password123", "role": "user"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "magni", "password": "password123"})
    r = client.get("/api/admin/users")
    assert r.status_code == 403
```

- [ ] **Step 3: Update router.py**

Add admin_routes router.

- [ ] **Step 4: Run tests**

Run: `python3 -m pytest tests/test_api_admin.py -v`
Expected: 8 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/api/admin_routes.py src/api/router.py tests/test_api_admin.py
git commit -m "feat: admin routes (list, create, delete, reset password users)"
```

---

## Task 4: Scope existing routes by user

**Files:**
- Modify: `src/api/vault_routes.py`, `src/api/connectors.py`, `src/api/accounts.py`, `src/api/portfolio.py`, `src/api/snapshots.py`, `src/api/transactions.py`, `src/api/performance.py`, `src/api/events.py`, `src/api/health.py`

- [ ] **Step 1: Update all data routes to use Depends(get_current_user)**

Every route that reads/writes user data gets a `user: AuthUser = Depends(get_current_user)` parameter. Replace:
- `deps.vault` → `deps.get_vault(user.id)`
- `deps.db_engine` → `deps.get_ledger(user.id)`
- `deps.manager.get_status(cid)` → `deps.manager.get_status(f"{user.id}:{cid}")`
- `deps.manager.spawn(cid, ...)` → `deps.manager.spawn(f"{user.id}:{cid}", ...)`
- `deps.manager.get_all_live_data()` → `deps.manager.get_user_live_data(user.id)`

- [ ] **Step 2: Update src/manager.py**

Add `stop_user_workers(user_id)` and `get_user_live_data(user_id)` methods.

- [ ] **Step 3: Update src/scheduler.py**

Group workers by user_id, write snapshots to the correct user's ledger.

- [ ] **Step 4: Update SSE events.py**

Filter events by user — extract user from cookie in the SSE endpoint.

- [ ] **Step 5: Run all tests**

Run: `python3 -m pytest tests/ -v`
Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add src/api/ src/manager.py src/scheduler.py
git commit -m "feat: scope all routes by user (vault, connectors, data, SSE)"
```

---

## Task 5: Data migration (single-user → multi-user)

**Files:**
- Modify: `src/main.py`

- [ ] **Step 1: Add migration logic in lifespan**

On startup, if `data/vault.db` or `data/ledger.db` exist (old single-user format):
- After admin setup, move them to `data/users/{admin_id}/`
- Log a message about the migration

```python
def migrate_legacy_data(admin_id: str):
    """Move old single-user data to the admin's user directory."""
    from src.config import VAULT_DB, LEDGER_DB, USERS_DIR
    import shutil
    user_dir = USERS_DIR / admin_id
    user_dir.mkdir(parents=True, exist_ok=True)
    if VAULT_DB.exists():
        shutil.move(str(VAULT_DB), str(user_dir / "vault.db"))
    if LEDGER_DB.exists():
        shutil.move(str(LEDGER_DB), str(user_dir / "ledger.db"))
```

Call this from `auth_setup` after creating the admin user.

- [ ] **Step 2: Commit**

```bash
git add src/main.py src/api/auth_routes.py
git commit -m "feat: migrate legacy single-user data to admin user directory"
```

---

## Task 6: Frontend auth

**Files:**
- Create: `frontend/src/pages/Login.tsx`, `frontend/src/hooks/useAuth.ts`, `frontend/src/pages/AdminUsers.tsx`
- Modify: `frontend/src/api/client.ts`, `frontend/src/hooks/useSSE.ts`, `frontend/src/App.tsx`, `frontend/src/context/AppContext.tsx`, `frontend/src/layouts/Sidebar.tsx`

- [ ] **Step 1: Update frontend/src/api/client.ts**

Add `credentials: 'same-origin'` to all fetch calls so the JWT cookie is sent.

- [ ] **Step 2: Update frontend/src/hooks/useSSE.ts**

Add `withCredentials: true` to EventSource.

- [ ] **Step 3: Create frontend/src/hooks/useAuth.ts**

Hook that calls `/api/auth/status` and manages auth state.

- [ ] **Step 4: Create frontend/src/pages/Login.tsx**

Login page with username + password fields, dark theme, gold accents.

- [ ] **Step 5: Update frontend/src/App.tsx**

Route based on auth state: `no_admin` → setup, `logged_out` → login, `logged_in` → vault check → dashboard.

- [ ] **Step 6: Update frontend/src/context/AppContext.tsx**

Add auth state, user info, logout handler.

- [ ] **Step 7: Update frontend/src/layouts/Sidebar.tsx**

Show username, role badge, logout button, admin link if admin.

- [ ] **Step 8: Create frontend/src/pages/AdminUsers.tsx**

Admin user management page (list, create, delete, reset password). Add as section in Settings or as separate page.

- [ ] **Step 9: Build and test**

Run: `cd frontend && bun run build`

- [ ] **Step 10: Commit**

```bash
git add frontend/
git commit -m "feat: frontend auth (login, admin users, credentials cookie, sidebar user)"
```

---

## Task 7: Final integration + push

- [ ] **Step 1: Run all backend tests**

Run: `python3 -m pytest tests/ -v`

- [ ] **Step 2: Build frontend**

Run: `cd frontend && bun run build`

- [ ] **Step 3: Manual test flow**

1. `./start.sh --reset`
2. Page setup admin → créer compte
3. Vault setup → vault unlock
4. Ajouter connecteur TR → 2FA → données
5. Logout → login → vault unlock → données toujours là
6. Admin → créer user "magni" → logout → login magni → vault setup séparé

- [ ] **Step 4: Commit and push**

```bash
git push
```
