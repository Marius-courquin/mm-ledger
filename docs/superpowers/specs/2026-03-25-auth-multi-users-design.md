# Auth & Multi-utilisateurs

> Spec validée le 2026-03-25. Système d'authentification multi-utilisateurs avec isolation complète des données.

## Vue d'ensemble

Ajout d'un système de login avec comptes utilisateurs (admin/user), sessions JWT, et isolation complète des données par utilisateur. Chaque user a son propre vault (SQLCipher) et sa propre base de données (SQLite). Le vault password est dissocié du password de login.

---

## Stockage

```
data/
├── app.db                  # Comptes users + clé JWT (SQLite, non chiffré)
├── users/
│   ├── {user_id}/
│   │   ├── vault.db        # Credentials chiffrés (SQLCipher, vault password du user)
│   │   └── ledger.db       # Snapshots, transactions, performance
│   ├── {user_id}/
│   │   ├── vault.db
│   │   └── ledger.db
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

CREATE TABLE app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- Stocke la clé secrète JWT dans app_config: key='jwt_secret', value='<random 64 chars>'
```

---

## Flow utilisateur

```
App load
  │
  GET /api/auth/status
  │
  ├─ "no_admin"       → Page "Créer le compte admin"
  │                       POST /api/auth/setup {username, password}
  │                       → Crée l'admin + génère jwt_secret
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

---

## JWT

| Champ | Valeur |
|---|---|
| Stockage | Cookie `mm_session`, `HttpOnly`, `Secure` (en prod), `SameSite=Lax` |
| Payload | `{user_id, username, role, exp}` |
| Expiration | 24h |
| Signature | HMAC-SHA256, clé secrète dans `app.db` `app_config` |
| Refresh | Pas de refresh token. Expiration = re-login |

---

## Routes API

### Auth (publiques, pas de JWT requis)

#### `GET /api/auth/status`

Retourne l'état global d'authentification.

```json
{"state": "no_admin"}       // Premier lancement
{"state": "logged_out"}     // Admin existe mais pas de session
{"state": "logged_in", "user": {"id": "xxx", "username": "marius", "role": "admin"}}
```

#### `POST /api/auth/setup`

Premier lancement. Crée le compte admin.

**Request:**
```json
{"username": "marius", "password": "monpassword"}
```

**Response 201:**
```json
{"status": "created", "user": {"id": "xxx", "username": "marius", "role": "admin"}}
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
{"status": "ok", "user": {"id": "xxx", "username": "marius", "role": "admin"}}
```
+ Set-Cookie: `mm_session=<JWT>`

**401:** identifiants incorrects.

#### `POST /api/auth/logout`

Clear le cookie.

**Response 200:**
```json
{"status": "logged_out"}
```

### Admin (JWT requis, role=admin)

#### `GET /api/admin/users`

Liste tous les utilisateurs.

```json
[
  {"id": "xxx", "username": "marius", "role": "admin", "created_at": "2026-03-25T..."},
  {"id": "yyy", "username": "magni", "role": "user", "created_at": "2026-03-25T..."}
]
```

#### `POST /api/admin/users`

Créer un nouvel utilisateur.

**Request:**
```json
{"username": "magni", "password": "sonpassword", "role": "user"}
```

**Response 201:**
```json
{"id": "yyy", "username": "magni", "role": "user"}
```

**409:** username déjà pris.

#### `DELETE /api/admin/users/{id}`

Supprime un utilisateur et toutes ses données (vault, ledger, workers).

**Response 204**

**403:** ne peut pas supprimer son propre compte.

### Routes existantes (JWT requis)

Toutes les routes existantes (`/api/vault/*`, `/api/connectors/*`, `/api/accounts/*`, `/api/portfolio/*`, etc.) sont **scopées au user connecté** via le JWT. Aucun changement d'interface, juste le scope des données change.

---

## Middleware auth

```python
# Appliqué sur toutes les routes sauf /api/auth/*
def get_current_user(request: Request) -> User:
    token = request.cookies.get("mm_session")
    if not token:
        raise HTTPException(401, "Non authentifié")
    payload = jwt.decode(token, secret, algorithms=["HS256"])
    return User(id=payload["user_id"], username=payload["username"], role=payload["role"])

def require_admin(user: User):
    if user.role != "admin":
        raise HTTPException(403, "Accès réservé aux administrateurs")
```

---

## Impact sur l'existant

### deps.py

```python
# Avant
vault: Vault | None = None
manager: ConnectorManager | None = None
db_engine = None

# Après
app_db = None                                    # app.db engine (users, config)
_user_vaults: dict[str, Vault] = {}              # user_id → Vault
_user_engines: dict[str, Engine] = {}            # user_id → ledger engine
manager: ConnectorManager | None = None          # global, workers tagués par user_id

def get_vault(user_id: str) -> Vault: ...
def get_ledger(user_id: str) -> Engine: ...
```

### Vault

Inchangé. Chaque user a son propre fichier `data/users/{user_id}/vault.db`.

### ConnectorManager

Les workers sont tagués par `user_id`. Un user ne peut interagir qu'avec ses propres workers.

```python
# Les connector_ids deviennent: {user_id}:{connector_id}
# Exemple: "abc123:trade_republic"
```

### Routes existantes

Chaque route reçoit le `user_id` du JWT et scope ses requêtes DB / vault / manager à ce user.

---

## Fichiers à créer/modifier

### Créer
- `src/auth.py` — User model, JWT encode/decode, password hashing
- `src/db/app_db.py` — app.db engine + users table
- `src/api/auth_routes.py` — /api/auth/* routes
- `src/api/admin_routes.py` — /api/admin/* routes
- `src/api/middleware.py` — JWT middleware, get_current_user
- `tests/test_auth.py`
- `tests/test_api_auth.py`
- `frontend/src/pages/Login.tsx`
- `frontend/src/pages/AdminUsers.tsx`
- `frontend/src/hooks/useAuth.ts`

### Modifier
- `src/main.py` — init app.db dans lifespan, ajouter middleware
- `src/api/deps.py` — get_vault(user_id), get_ledger(user_id)
- `src/api/router.py` — ajouter auth + admin routers
- `src/api/vault_routes.py` — scope par user
- `src/api/connectors.py` — scope par user
- `src/api/accounts.py` — scope par user
- `src/api/portfolio.py` — scope par user
- `src/api/snapshots.py` — scope par user
- `src/api/transactions.py` — scope par user
- `src/api/performance.py` — scope par user
- `src/api/events.py` — filtrer SSE par user
- `src/api/health.py` — scope workers par user
- `frontend/src/App.tsx` — routing auth
- `frontend/src/context/AppContext.tsx` — auth state
- `frontend/src/layouts/Sidebar.tsx` — afficher user, lien admin
- `pyproject.toml` — ajouter bcrypt, PyJWT

### Dépendances ajoutées
- `bcrypt` — hashing password
- `PyJWT` — JWT encode/decode

---

## Sécurité

| Règle | Implémentation |
|---|---|
| Passwords hashés | bcrypt avec salt auto (12 rounds) |
| JWT HttpOnly | Cookie non accessible par JS |
| Pas de password dans les réponses | Jamais retourné, même pour l'admin |
| Isolation données | Chaque user a son propre dossier data/ |
| Suppression complète | DELETE user supprime vault.db + ledger.db + arrête les workers |
| Rate limiting login | 5 tentatives / 5 min par username |

---

## Pages frontend

### Login (`/login`)
- Champ username + password
- Bouton "Se connecter"
- Lien vers setup si premier lancement
- Design dans le style mm-ledger (dark, gold accents)

### Setup Admin (`/setup`)
- Même design que vault setup
- Champ username + password + confirmation
- "Créer le compte administrateur"

### Admin Users (`/admin/users`)
- Accessible depuis Settings (onglet ou section)
- Liste des users avec role + date de création
- Bouton "Ajouter un utilisateur"
- Bouton supprimer avec confirmation
- Formulaire: username, password, role (user/admin)
