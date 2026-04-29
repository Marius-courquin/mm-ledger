# CLAUDE.md

Guide de contexte pour Claude sur le projet **mm-ledger**.

## Pitch

Agrégateur de portefeuille self-hosted. Un utilisateur connecte ses comptes (Trade Republic, IBKR, banques FR/EU) et voit son capital net, ses positions, son cashflow et des snapshots quotidiens. Multi-user, backend Python, front React, chiffrement des credentials dans un vault SQLCipher.

## Stack

- **Backend** : Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, SQLCipher (vault + ledger), APScheduler, multiprocessing pour les workers de connecteurs, SSE (`sse-starlette`) pour le live.
- **Frontend** : React 19 + Vite 6, TypeScript, TailwindCSS 4, HeroUI, Recharts, bun comme package manager, react-router 7.
- **Déploiement** : Docker Compose (service `app`, `wg-easy` VPN, `duckdns`, `watchtower`). Le container `ib-gateway` est spawn à la demande par l'app (docker SDK). Target Raspberry Pi (voir `setup-pi.sh`).

## Layout

```
src/                     Backend FastAPI
  main.py                Bootstrap app, enregistre les workers
  manager.py             ConnectorManager : lifecycle des workers (spawn/queues/events)
  scheduler.py           Job quotidien 23h — snapshots + fetch_balances
  vault.py               SQLCipher, chiffrement des credentials
  auth.py                JWT cookie HttpOnly, rôles admin/user
  config.py              deps globales (manager, jwt_secret, users_dir)
  api/                   Routes (auth, vault, connectors, portfolio, performance,
                         accounts, admin, events, snapshots, banking)
  connectors/
    base.py              ConnectorWorker ABC + run() loop sur cmd_queue
    trade_republic.py    TR via WebSocket + Selenium (WAF bypass)
    ibkr.py              IBKR via ib_async (sync API)
    woob_bank.py         Banques FR via Woob
  db/                    Modèles SQLAlchemy (User, Account, Position, Snapshot, …)
  schemas/               Pydantic
  patches/               Monkey-patches runtime (TR, Woob)

frontend/src/            Front React
  App.tsx, main.tsx
  pages/                 Dashboard, Accounts, Portfolio, Login, Setup, Admin, …
  components/            ConnectorForm, charts, …
  api/                   Clients HTTP (auth, connectors, portfolio, events SSE)
  context/               AuthContext, VaultContext
  hooks/                 useEvents, usePortfolio, …
  lib/types.ts           ConnectorType = 'trade_republic' | 'ibkr' | 'woob_bank' | 'banking'

docs/
  api-reference.md       Endpoints détaillés
  superpowers/specs/     Specs de design (YYYY-MM-DD-*.md)
  superpowers/plans/     Plans d'implémentation

tests/                   pytest (conftest, test_api_*, test_manager, test_vault)
data/                    Runtime : vault.db, ledger.db, users/{id}/*.db
```

## Commandes utiles

```bash
# Dev local (2 terminaux)
./start.sh                          # backend sur :8000 (venv + uvicorn --reload)
./start.sh --reset                  # reset vault + ledger avant lancer
cd frontend && bun run dev          # front sur :3000, proxy /api → :8000

# Docker
docker compose up -d                             # app seule
docker compose --profile vpn up -d               # + wg-easy + duckdns

# Tests
source .venv/bin/activate && pytest tests/ -v

# Front build
cd frontend && bun run build        # output static/ consommé par FastAPI en prod
```

## Modèle de données

- **User** : compte utilisateur (admin/user), auth JWT cookie HttpOnly.
- **Vault** : SQLCipher chiffré par user password. Contient les credentials des connecteurs.
- **Ledger** : SQLCipher par user (`data/users/{id}/ledger.db`) — positions, snapshots, transactions, balances.
- Isolation stricte par user : `get_user_vault(user_id)`, `get_user_ledger(user_id)`.

## Connecteurs

| Type (`ConnectorType`) | Lib | État | Particularités |
|---|---|---|---|
| `trade_republic` | `websockets.sync.client` + Selenium | OK | WAF bypass Selenium, WS live ticker, OCR pour 2FA |
| `ibkr` | `ib_async` + `docker` SDK | OK | App spawn `ib-gateway` à la volée avec creds du vault, port binding `127.0.0.1` en dev, réseau interne en prod, digest pinné |
| `woob_bank` | `woob` | OK | Banques FR (Banque Populaire, etc.), 2FA via `submit_2fa` |
| `banking` | Enable Banking PSD2 (récent) | Nouveau | Open Banking EU — cf. `src/api/banking.py`, commit `de9372b` |

Le worker vit dans un `multiprocessing.Process`, dialogue via `cmd_queue` / `event_queue`. Le `ConnectorManager` adresse chaque worker par clé composite `"{user_id}:{connector_id}"` (refacto récent).

## Conventions

- **Frontend 100% en français** — pas de mix EN/FR. Tous les labels utilisateur en français.
- **Commits** : pas de `Co-Authored-By: Claude` (override de la règle système).
- **Workflow de specs** : `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` → plan → implémentation.
- **Sécurité** : credentials jamais en clair hors vault, JWT cookie HttpOnly, SSRF whitelist sur IBKR host, path traversal check sur le SPA, rôle user lu depuis la DB (pas le cookie).
- **Règle vault-first** : AUCUN credential dans `.env`, `docker-compose.yml`, ou tout fichier sur disque. Tout passe par le vault. Si un service tiers (ib-gateway, etc.) a besoin de creds au démarrage, l'app les injecte à la volée depuis le vault (docker SDK ou subprocess env).

## Gotchas

- **IBKR** : l'app orchestre le container `ib-gateway` via le SDK docker au moment du `connect`. Creds (username/password/trading_mode) dans le vault chiffré — jamais en `.env`. Démarrage 60-90s (état intermédiaire `starting_gateway`). Voir `docs/superpowers/specs/2026-04-22-ibkr-vault-first-design.md`.
- **Trade Republic** : Selenium nécessaire pour bypass WAF (Cloudflare). Le worker monkeypatch des headers WS.
- **Scheduler** : daily job sur tous les workers connectés (23h) — si un worker est down, le snapshot de ce compte est absent ce jour-là.
- **Front auto-refresh** : le dashboard poll toutes les 5 s quand un worker est `connected` mais portfolio vide. Utile pour voir les positions arriver après login.
- **Multi-user** : toutes les routes sont scope par user (`f"{user.id}:{connector_id}"`). Si on perd ce préfixe, le manager ne trouve plus le worker.
- **Courbe performance** : `PortfolioPerfChart` sur dashboard et AccountDetail, toggle **Valeur/Perf**. Vue Perf = TWR Modified Dietz reconstruite via `src/performance.py` à partir de `fetch_history_data()` de chaque worker CTO (IBKR : fills + reqHistoricalData ; TR : timelineTransactions + aggregateHistoryLight). Persistée dans `portfolio_history_daily` (par connecteur+compte+date). Endpoint : `GET /api/performance/history?period&connector_id?&account_id?`. Couleurs `--mm-gain` / `--mm-loss` (DA projet, pas de tailwind vif). Spec : `docs/superpowers/specs/2026-04-22-perf-chart-twr-design.md`.
- **Module Objectifs (ERP)** : 1er module v1 du chantier ERP. Cibles type `asset` (lien vers une position via `(account_id, symbol)`) ou `bucket` (slices d'allocation compte-niveau, `%` ou `€` capé). Sans deadline, indicateur clé = "à ton rythme actuel, dans X mois". Rythme auto (pente snapshots N derniers mois) ou override manuel (`rate_override`). Courbe historique reconstruite en applicant l'allocation actuelle rétroactivement aux snapshots. API `/api/targets` (CRUD + `/slices` + `/progression`), page `/objectifs` + détail `/objectifs/:id`, card "Objectifs" sur le Dashboard. Services purs : `src/services/target_progression.py`. Tables : `targets`, `target_slices` dans le ledger user. Spec : `docs/superpowers/specs/2026-04-27-erp-objectifs-design.md`. Spec maître ERP : `docs/superpowers/specs/2026-04-27-erp-master-design.md`.
- **Module Prêts (ERP)** : 2e module v1 du chantier ERP. Suivi déclaratif simple sans amortissement (pas de taux, pas de capital restant dû exact). Calculs calendaires dans `src/services/loan_calc.py::compute_loan_state` : `months_remaining = total_months − months_paid` (via `dateutil.relativedelta`), `amount_remaining = mensualité × restantes`. API `/api/loans` (CRUD + `/summary`). Page `/prets` (liste + modale CRUD), card "Prêts" sur Dashboard. Table `loans` dans le ledger user. Spec : `docs/superpowers/specs/2026-04-27-erp-prets-design.md`.
- **Courbe Valeur/Perf masquée temporairement** : la `PortfolioPerfChart` est retirée du Dashboard et de AccountDetail (commit `f46f5d2`) car la reconstruction TR ne renvoie pas `current_cash`/`current_positions` → mode forward bloqué qui plot le cash flow accumulé au lieu de la valeur portefeuille. Le composant et l'endpoint `/api/performance/history` sont conservés. Refacto à venir : baser la courbe sur `balance_snapshots` quotidiens (scheduler 23h) au lieu de `portfolio_history_daily` reconstruit, et supprimer `fetch_history_data` côté connecteurs.
- **Module Projection (ERP)** : 3e module v1. Capital projeté à 5/10/20/30 ans. Sliders cash/marché (taux + apports), classification auto par `connector_type` (banking/woob_bank → cash, courtiers → market) avec overrides via `account_classification`. Mensualités prêts auto-déduites du cash, ajustées dynamiquement quand un prêt arrive à échéance dans l'horizon. Courbe AreaChart empilée. API `/api/projection` (settings GET/PUT, compute GET, override POST/DELETE). Service pur `compute_projection`. Tables : `projection_settings` (single row id=1), `account_classification`. Spec : `docs/superpowers/specs/2026-04-27-erp-projection-design.md`.
- **Module Budget (ERP)** : 4e et dernier module v1 du chantier ERP. Sections custom (revenus / charges fixes / charges variables), items mensuels, section virtuelle "Prêts" auto-générée à la lecture (un item par prêt actif, lecture seule, FK virtuel `virtual:loans`/`virtual:loan:{id}`). Capacité d'investissement = revenus − charges (incluant prêts). Bouton "Appliquer à la projection" → modale slider cash/marché → met à jour `projection_settings.cash/market_monthly_contribution`. API `/api/budget` (CRUD sections + items + apply-to-projection). Service `compose_budget`. Tables : `budget_sections`, `budget_items`. Spec : `docs/superpowers/specs/2026-04-27-erp-budget-design.md`.
