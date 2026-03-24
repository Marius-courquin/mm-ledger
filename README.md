# mm-ledger

Aggregateur de portefeuille self-hosted. Backend Python (FastAPI) qui connecte Trade Republic, Interactive Brokers, et les banques francaises (Woob).

## Quick Start (macOS)

### 1. Prerequisites

```bash
brew install sqlcipher tesseract
```

### 2. Virtual env + dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Si `sqlcipher3` fail a l'install :
```bash
SQLCIPHER_PATH=$(brew --prefix sqlcipher)
C_INCLUDE_PATH="$SQLCIPHER_PATH/include" LIBRARY_PATH="$SQLCIPHER_PATH/lib" pip install sqlcipher3
```

### 3. Lancer le serveur

```bash
source .venv/bin/activate
uvicorn src.main:app --reload --port 8000
```

Le serveur demarre sur `http://localhost:8000`. Swagger UI sur `http://localhost:8000/docs`.

### 4. Premier lancement

```bash
# Verifier l'etat
curl http://localhost:8000/api/vault/status
# {"state":"uninitialized"}

# Creer le vault avec un master password
curl -X POST http://localhost:8000/api/vault/setup \
  -H "Content-Type: application/json" \
  -d '{"password": "ton_mot_de_passe"}'

# Deverrouiller
curl -X POST http://localhost:8000/api/vault/unlock \
  -H "Content-Type: application/json" \
  -d '{"password": "ton_mot_de_passe"}'
```

### 5. Ajouter un connecteur

```bash
# Trade Republic
curl -X POST http://localhost:8000/api/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "tr_charles",
    "type": "trade_republic",
    "label": "TR Charles",
    "credentials": {"phone": "+33XXXXXXXXX", "pin": "XXXX"},
    "config": {}
  }'

# Banque Populaire
curl -X POST http://localhost:8000/api/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "bp_rives",
    "type": "woob_bank",
    "label": "BP Rives de Paris",
    "credentials": {
      "login": "XXXXXXXX",
      "password": "XXXXXXXX",
      "bank_module": "banquepopulaire",
      "region": "10207"
    },
    "config": {}
  }'

# Interactive Brokers (necessite IB Gateway Docker)
curl -X POST http://localhost:8000/api/connectors \
  -H "Content-Type: application/json" \
  -d '{
    "id": "ibkr_main",
    "type": "ibkr",
    "label": "IBKR",
    "credentials": {"host": "127.0.0.1", "port": 4001},
    "config": {}
  }'
```

### 6. Connecter un worker

```bash
# Lancer la connexion
curl -X POST http://localhost:8000/api/connectors/tr_charles/connect

# Suivre l'etat (poll ou SSE)
curl http://localhost:8000/api/connectors/tr_charles/status

# Soumettre le code 2FA quand state = "waiting_2fa"
curl -X POST http://localhost:8000/api/connectors/tr_charles/2fa \
  -H "Content-Type: application/json" \
  -d '{"code": "123456"}'
```

### 7. Consulter les donnees

```bash
curl http://localhost:8000/api/accounts
curl http://localhost:8000/api/accounts/tr_CTO_EUR/balance
curl http://localhost:8000/api/portfolio
curl "http://localhost:8000/api/snapshots?from=2026-03-01&to=2026-03-31"
curl "http://localhost:8000/api/transactions?from=2026-03-01"
curl -X POST http://localhost:8000/api/snapshots/trigger
curl http://localhost:8000/api/health
```

### 8. SSE (live updates)

```bash
curl -N http://localhost:8000/api/events
```

## Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## IB Gateway (optionnel)

```bash
IBKR_USERNAME=ton_user IBKR_PASSWORD=ton_pass docker compose up ib-gateway -d
```

## Endpoints

| Methode | Route | Description |
|---------|-------|-------------|
| GET | `/api/vault/status` | Etat du vault |
| POST | `/api/vault/setup` | Creer le vault |
| POST | `/api/vault/unlock` | Deverrouiller |
| POST | `/api/vault/lock` | Verrouiller |
| GET | `/api/connectors` | Connecteurs + etat workers |
| GET | `/api/connectors/types` | Types disponibles + champs |
| POST | `/api/connectors` | Ajouter un connecteur |
| POST | `/api/connectors/{id}/connect` | Lancer le worker |
| POST | `/api/connectors/{id}/2fa` | Soumettre code 2FA |
| GET | `/api/accounts` | Tous les comptes |
| GET | `/api/accounts/{id}/balance` | Balance d'un compte |
| GET | `/api/portfolio` | Positions agregees |
| GET | `/api/snapshots` | Historique quotidien |
| GET | `/api/transactions` | Mouvements |
| GET | `/api/performance` | P&L par periode |
| GET | `/api/events` | SSE live stream |
| GET | `/api/health` | Healthcheck |
| GET | `/docs` | Swagger UI |

Ref complete : `docs/api-reference.md`
