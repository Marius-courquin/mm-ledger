# mm-ledger

Aggregateur de portefeuille self-hosted. Backend Python (FastAPI) + frontend React, connecte Trade Republic, Interactive Brokers, et les banques francaises (Woob).

## Deploiement Docker (recommande)

```bash
docker compose up -d
```

L'app est accessible sur `http://localhost:8000`. Le premier lancement affiche la page de creation du compte admin.

Pour IBKR (optionnel) :
```bash
IBKR_USERNAME=user IBKR_PASSWORD=pass docker compose --profile ibkr up -d
```

## Developpement local (macOS)

### Prerequisites

```bash
brew install sqlcipher tesseract
```

### Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn src.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
bun install
bun run dev
```

Le front dev tourne sur `http://localhost:3000` et proxy `/api` vers `:8000`.

### Tout en un

```bash
./start.sh           # lance le backend
./start.sh --reset   # reset les donnees et relance
```

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## Premier lancement

1. Creer le compte administrateur (username + mot de passe)
2. Creer le vault (mot de passe de chiffrement des credentials bancaires)
3. Ajouter un connecteur (Trade Republic, Banque Populaire, IBKR)
4. Se connecter au connecteur (2FA si necessaire)
5. Consulter le portfolio

## Architecture

```
docker compose up
  ├── app (FastAPI + React build, port 8000)
  │   ├── /api/*        → Backend Python
  │   └── /*            → Frontend React (SPA)
  └── ib-gateway (optionnel, profil ibkr)
```

- **Auth** : multi-utilisateurs, JWT cookie HttpOnly, roles admin/user
- **Donnees** : isolees par user (`data/users/{id}/vault.db + ledger.db`)
- **Connecteurs** : Trade Republic (WS + Selenium WAF bypass), IBKR (ib_async), Banques FR (Woob)
- **Snapshots** : scheduler quotidien 23h00

## Endpoints

| Route | Description |
|-------|-------------|
| `GET /api/auth/status` | Etat authentification |
| `POST /api/auth/setup` | Creer le compte admin |
| `POST /api/auth/login` | Se connecter |
| `POST /api/auth/logout` | Se deconnecter |
| `GET /api/admin/users` | Gestion utilisateurs (admin) |
| `GET /api/vault/status` | Etat du vault |
| `POST /api/vault/setup` | Creer le vault |
| `POST /api/vault/unlock` | Deverrouiller |
| `GET /api/connectors` | Connecteurs + etat workers |
| `GET /api/portfolio` | Portefeuille par compte |
| `GET /api/accounts` | Comptes |
| `GET /api/snapshots` | Historique |
| `GET /api/events` | SSE live stream |
| `GET /api/health` | Healthcheck |
| `GET /docs` | Swagger UI |

Ref complete : `docs/api-reference.md`
