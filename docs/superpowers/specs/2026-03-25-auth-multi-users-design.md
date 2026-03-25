# Auth & Multi-utilisateurs

> Spec validée le 2026-03-25. Système d'authentification multi-utilisateurs avec isolation complète des données.

## Vue d'ensemble

Ajout d'un système de login avec comptes utilisateurs (admin/user), sessions JWT, et isolation complète des données par utilisateur. Chaque user a son propre vault (SQLCipher) et sa propre base de données (SQLite). Le vault password est dissocié du password de login.

---

## Stockage

```
data/
├── app.db                  # Comptes users (SQLite, non chiffré)
├── .jwt_secret             # Clé JWT (fichier 0600, pas en DB)
├── users/
│   ├── {user_id}/
│   │   ├── vault.db        # Credentials chiffrés (SQLCipher, vault password du user)
│   │   └── ledger.db       # Snapshots, transactions, performance
```

### `app.db` — Table users

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,            -- UUID
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,     -- bcrypt
    role TEXT NOT NULL DEFAULT 'user',  -- 'admin' | 'user'
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Clé JWT

Fichier `data/.jwt_secret` avec permissions `0600`. Généré au premier lancement (64 chars random). Pas stocké en DB — un accès DB ne permet pas de forger des tokens.

### Modèle de menace

L'app tourne sur un réseau local derrière VPN. L'accès filesystem est considéré comme trusted (si quelqu'un a accès au disque, il a tout). `app.db` contient des bcrypt hashes (irréversibles) et des usernames. Les vrais secrets (credentials bancaires) sont dans les vaults SQLCipher par user, protégés par un mot de passe séparé.

---

## Flow utilisateur

```
App load
  │
  GET /api/auth/status
  │
  ├─ "no_admin"       → Page "Créer le compte admin"
  │                       POST /api/auth/setup {username, password}
  │                       → Crée l'admin + génère .jwt_secret
  │                       → Auto-login (set cookie)
  │                       → Redirige vers vault setup
  │
  ├─ "logged_out"     → Page login
  │                       POST /api/auth/login {username, password}
  │                       → Set cookie JWT HttpOnly
  │                       → Check vault status du user
  │
  └─ "logged_in"      → Check vault
       │
       ├─ vault "uninitialized"  → Page vault setup
       ├─ vault "locked"         → Page vault unlock
       └─ vault "unlocked"       → Dashboard
```

`GET /api/auth/status` : l'état `logged_in` n'est retourné que si la requête porte un cookie JWT valide. Sans cookie → toujours `logged_out` ou `no_admin`.

---

## JWT

| Champ | Valeur |
|---|---|
| Stockage | Cookie `mm_session`, `HttpOnly`, `SameSite=Lax` |
| Payload | `{user_id, username, role, exp}` |
| Expiration | 24h |
| Signature | HMAC-SHA256, clé dans `data/.jwt_secret` |
| Flag Secure | Activé si env var `SECURE_COOKIES=1` ou si scheme HTTPS détecté |

---

## Routes API

### Auth (publiques, pas de JWT requis)

#### `GET /api/auth/status`

Semi-authentifié : lit le cookie JWT si présent.

```json
{"state": "no_admin"}                                                    // Pas d'admin en DB
{"state": "logged_out"}                                                  // Admin existe, pas de session
{"state": "logged_in", "user": {"id": "x", "username": "marius", "role": "admin"}}  // Cookie valide
```

#### `POST /api/auth/setup`

Premier lancement. Crée le compte admin + génère la clé JWT.

**Request:**
```json
{"username": "marius", "password": "monpassword"}
```

**Validation :** username 3+ chars, password 8+ chars.

**Response 201:**
```json
{"status": "created", "user": {"id": "x", "username": "marius", "role": "admin"}}
```
+ Set-Cookie: `mm_session=<JWT>`

**409:** un admin existe déjà.

#### `POST /api/auth/login`

**Request:**
```json
{"username": "marius", "password": "monpassword"}
```

**Response 200:**
```json
{"status": "ok", "user": {"id": "x", "username": "marius", "role": "admin"}}
```
+ Set-Cookie: `mm_session=<JWT>`

**401:** identifiants incorrects.
**429:** rate limit (5 tentatives / 5 min par username, compteur in-memory, reset au succès et au restart serveur).

#### `POST /api/auth/logout`

Clear le cookie. Lock le vault du user. Stop ses workers.

**Response 200:**
```json
{"status": "logged_out"}
```

### Admin (JWT requis, role=admin)

#### `GET /api/admin/users`

```json
[
  {"id": "x", "username": "marius", "role": "admin", "created_at": "2026-03-25T..."},
  {"id": "y", "username": "magni", "role": "user", "created_at": "2026-03-25T..."}
]
```

#### `POST /api/admin/users`

**Request:**
```json
{"username": "magni", "password": "sonpassword", "role": "user"}
```

**Validation :** username 3+ chars, password 8+ chars, role in ('admin', 'user').

**Response 201:**
```json
{"id": "y", "username": "magni", "role": "user"}
```

**409:** username déjà pris.

#### `PUT /api/admin/users/{id}`

Reset le password d'un user (sans toucher à son vault).

**Request:**
```json
{"password": "newpassword"}
```

**Response 200:**
```json
{"status": "updated"}
```

#### `DELETE /api/admin/users/{id}`

Supprime un utilisateur, ses données, et invalide sa session.

- Stop les workers du user
- Lock et supprime le vault du user
- Supprime le dossier `data/users/{id}/`
- Ajoute le `user_id` à un deny set in-memory (vérifié par le middleware)

**Response 204**

**403:** ne peut pas supprimer le dernier admin.

### Routes existantes (JWT requis)

Toutes les routes existantes sont **scopées au user connecté** via le JWT. Le `user_id` du token détermine quel vault, quel ledger, et quels workers sont accessibles. Aucun changement d'interface API.

Les routes vault (`/api/vault/*`) utilisent implicitement le `user_id` du JWT pour résoudre quel vault opérer.

---

## Middleware auth

```python
# Dépendance FastAPI injectée dans toutes les routes sauf /api/auth/*
async def get_current_user(request: Request) -> User:
    token = request.cookies.get("mm_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    payload = jwt.decode(token, get_jwt_secret(), algorithms=["HS256"])
    user_id = payload["user_id"]
    # Check deny set (user deleted while token still valid)
    if user_id in _denied_users:
        raise HTTPException(401, "Compte supprimé")
    return User(id=user_id, username=payload["username"], role=payload["role"])

def require_admin(user: User = Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
    return user
```

---

## Impact sur l'existant

### deps.py

```python
app_db = None                                    # app.db engine
_user_vaults: dict[str, Vault] = {}              # user_id → Vault (lazy, créé au premier accès)
_user_engines: dict[str, Engine] = {}            # user_id → ledger engine (lazy, pool_size=1)
manager: ConnectorManager | None = None          # global

def get_vault(user_id: str) -> Vault:
    """Retourne le vault du user, le crée si nécessaire."""
    if user_id not in _user_vaults:
        path = DATA_DIR / "users" / user_id / "vault.db"
        _user_vaults[user_id] = Vault(path)
    return _user_vaults[user_id]

def get_ledger(user_id: str) -> Engine:
    """Retourne le ledger engine du user, le crée si nécessaire. pool_size=1 pour limiter les file handles."""
    if user_id not in _user_engines:
        path = DATA_DIR / "users" / user_id / "ledger.db"
        _user_engines[user_id] = create_engine_and_tables(path)
    return _user_engines[user_id]

def cleanup_user(user_id: str):
    """Lock vault, dispose engine, remove from caches."""
    if user_id in _user_vaults:
        _user_vaults[user_id].lock()
        del _user_vaults[user_id]
    if user_id in _user_engines:
        _user_engines[user_id].dispose()
        del _user_engines[user_id]
```

### ConnectorManager

Workers tagués `{user_id}:{connector_id}`. Le manager reste un singleton global.

```python
# spawn("abc123:trade_republic", ...)
# stop("abc123:trade_republic")
# get_status("abc123:trade_republic")

def stop_user_workers(self, user_id: str):
    """Stop tous les workers d'un user."""
    for cid in list(self._workers):
        if cid.startswith(f"{user_id}:"):
            self.stop(cid)

def get_user_live_data(self, user_id: str) -> dict:
    """Retourne uniquement les données live du user."""
    self.collect_events()
    return {k.split(":", 1)[1]: v for k, v in self.live_data.items() if k.startswith(f"{user_id}:")}
```

### Scheduler

Le daily snapshot itère tous les users qui ont des workers connectés :

```python
async def daily_snapshot():
    health = deps.manager.health_check()
    # Group by user_id
    for composite_id, state in health.items():
        user_id, connector_id = composite_id.split(":", 1)
        if state != "connected":
            continue
        engine = deps.get_ledger(user_id)
        # ... fetch + upsert dans le ledger du user
```

### Logout cleanup

```python
@router.post("/logout")
def logout(response: Response, user: User = Depends(get_current_user)):
    # Stop workers
    deps.manager.stop_user_workers(user.id)
    # Lock vault + cleanup caches
    deps.cleanup_user(user.id)
    # Clear cookie
    response.delete_cookie("mm_session")
    return {"status": "logged_out"}
```

### Sessions concurrentes

Un user peut être connecté depuis plusieurs devices. Le vault in-memory est partagé entre ses sessions (un seul unlock suffit). Les workers tournent indépendamment des sessions.

### Frontend : `credentials: 'include'`

Le `fetch` dans `frontend/src/api/client.ts` doit inclure `credentials: 'same-origin'` pour que le cookie JWT soit envoyé. L'`EventSource` SSE doit utiliser `withCredentials: true`.

---

## Migration données existantes

Au premier lancement après la mise à jour, si `data/vault.db` et/ou `data/ledger.db` existent (ancien format single-user) :

1. L'app démarre et détecte les anciens fichiers
2. L'utilisateur crée le compte admin via `/api/auth/setup`
3. Les anciens fichiers sont déplacés vers `data/users/{admin_id}/`
4. Le vault reste locked — le user devra l'unlock avec son ancien vault password
5. Les anciens fichiers sont supprimés de `data/`

Si la migration échoue, les fichiers restent en place et un warning est loggé.

---

## Fichiers à créer/modifier

### Créer
- `src/auth.py` — User model, JWT encode/decode (python-jose, déjà installé), bcrypt hashing
- `src/db/app_db.py` — app.db engine + users table
- `src/api/auth_routes.py` — /api/auth/* routes
- `src/api/admin_routes.py` — /api/admin/* routes
- `src/api/middleware.py` — get_current_user, require_admin, deny set
- `tests/test_auth.py` — hashing, JWT, user model
- `tests/test_api_auth.py` — setup, login, logout, rate limit, migration
- `tests/test_api_admin.py` — CRUD users, permissions, last admin guard
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/AdminUsers.tsx`
- `frontend/src/hooks/useAuth.ts`

### Modifier
- `src/main.py` — init app.db, migration, middleware
- `src/api/deps.py` — get_vault(user_id), get_ledger(user_id), cleanup_user
- `src/api/router.py` — auth + admin routers
- `src/api/vault_routes.py` — scope par user (Depends get_current_user)
- `src/api/connectors.py` — scope par user
- `src/api/accounts.py` — scope par user
- `src/api/portfolio.py` — scope par user
- `src/api/snapshots.py` — scope par user
- `src/api/transactions.py` — scope par user
- `src/api/performance.py` — scope par user
- `src/api/events.py` — filtrer SSE par user, withCredentials
- `src/api/health.py` — scope workers par user
- `src/manager.py` — stop_user_workers, get_user_live_data
- `src/scheduler.py` — itérer par user
- `frontend/src/api/client.ts` — ajouter `credentials: 'same-origin'`
- `frontend/src/hooks/useSSE.ts` — `withCredentials: true`
- `frontend/src/App.tsx` — routing auth
- `frontend/src/context/AppContext.tsx` — auth state
- `frontend/src/layouts/Sidebar.tsx` — afficher user, lien admin, logout
- `pyproject.toml` — ajouter `bcrypt`

### Dépendances
- `bcrypt` — hashing password
- `python-jose` — déjà installé, utilisé pour JWT (pas besoin de PyJWT)

---

## Sécurité

| Règle | Implémentation |
|---|---|
| Passwords hashés | bcrypt 12 rounds |
| Password min length | 8 chars login, vault inchangé |
| Username min length | 3 chars |
| JWT HttpOnly | Cookie non accessible par JS |
| JWT secret hors DB | Fichier `data/.jwt_secret` permissions 0600 |
| Pas de password dans les réponses | Jamais retourné |
| Isolation données | Dossier séparé par user |
| Suppression complète | DELETE user → stop workers + delete files + deny session |
| Rate limiting login | 5 / 5min par username, in-memory, reset au succès |
| Dernier admin protégé | Impossible de supprimer le dernier admin |
| CSRF | SameSite=Lax suffisant (app locale, pas de cross-origin) |

---

## Pages frontend

### Login (`/login`)
- Champ username + password
- Bouton "Se connecter"
- Design mm-ledger (dark, gold)

### Setup Admin (`/setup`)
- Champ username + password + confirmation
- "Créer le compte administrateur"

### Admin Users (section dans `/settings`)
- Liste des users avec role + date
- Bouton "Ajouter un utilisateur"
- Bouton supprimer avec confirmation
- Formulaire: username, password, role
- Reset password par user
