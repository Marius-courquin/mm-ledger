# Dashboard Métriques — Capital NET, Courbe, Cashflow

> Spec validée le 2026-03-25.

## Vue d'ensemble

Ajout de 3 fonctionnalités au dashboard :
1. **Capital NET live** — somme de tout (banque + investissements)
2. **Courbe d'évolution** — snapshot quotidien + historique TR pour les investissements
3. **Cashflow mensuel** — delta + détail des transactions par source (BP, TR)

---

## 1. Capital NET

### Route `GET /api/net-worth`

Agrège les données live de tous les workers connectés du user.

```json
{
  "total": 25432.50,
  "currency": "EUR",
  "bank_total": 8500.00,
  "investments_total": 16932.50,
  "investments_pnl": 1200.00,
  "investments_pnl_pct": 7.62,
  "breakdown": [
    {"name": "Compte courant", "value": 5200.00, "source": "bp", "type": "bank"},
    {"name": "Livret A", "value": 3300.00, "source": "bp", "type": "bank"},
    {"name": "CTO", "value": 9500.00, "source": "tr", "type": "investment"},
    {"name": "PEA", "value": 7432.50, "source": "tr", "type": "investment"}
  ]
}
```

**Calcul :**
- Bank : somme des balances Woob (chaque compte a un `balance`)
- Investissements : somme des positions live TR/IBKR (value = qty * current_price) + cash TR
- `investments_pnl` = valeur positions - investi
- Pas de snapshot nécessaire, tout est live

---

## 2. Courbe d'évolution

### Table `net_worth_snapshots`

Ajoutée au ledger de chaque user :

```sql
CREATE TABLE net_worth_snapshots (
    date TEXT PRIMARY KEY,
    total REAL,
    bank_total REAL,
    investments_total REAL,
    breakdown JSON,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Scheduler 23h

Le `daily_snapshot` existant est étendu : après les snapshots par compte, il calcule le capital net et INSERT dans `net_worth_snapshots`.

### Route `GET /api/net-worth/history?from=&to=`

```json
[
  {"date": "2026-03-01", "total": 24500.00, "bank_total": 8200.00, "investments_total": 16300.00},
  {"date": "2026-03-02", "total": 24650.00, "bank_total": 8200.00, "investments_total": 16450.00},
  ...
]
```

Query params : `from` (défaut -30j), `to` (défaut aujourd'hui).

### Historique investissements TR

En complément des snapshots quotidiens, on fetch `userPortfolioChartModifiedDietz` via le WS TR. Ça donne l'historique détaillé des positions dès le premier jour (pas besoin d'attendre les snapshots).

Route : `GET /api/portfolio/chart?range=1m|3m|1y|max`

Le worker TR le fetch dans l'auto-fetch et le stocke dans les events.

---

## 3. Cashflow mensuel

### Route `GET /api/cashflow?month=2026-03`

```json
{
  "month": "2026-03",
  "delta": 487.50,
  "income": 3200.00,
  "expenses": -2712.50,
  "sources": [
    {
      "source": "bp",
      "label": "Banque Populaire",
      "delta": 612.50,
      "income": 3200.00,
      "expenses": -2587.50,
      "transactions": [
        {"date": "2026-03-01", "label": "Salaire", "amount": 3200.00, "type": "income"},
        {"date": "2026-03-05", "label": "Loyer", "amount": -800.00, "type": "expense"}
      ]
    },
    {
      "source": "tr",
      "label": "Trade Republic",
      "delta": -125.00,
      "income": 0,
      "expenses": -125.00,
      "transactions": [
        {"date": "2026-03-15", "label": "Restaurant", "amount": -45.00, "type": "expense"}
      ]
    }
  ]
}
```

### Fetch des transactions

**BP :** `woob_worker.fetch_transactions()` — déjà implémenté, retourne `{account_id, date, label, amount, type}`. Ajouté à l'auto-fetch après connexion.

**TR :** `timelineTransactions` via WS — déjà implémenté avec pagination. Filtré côté back pour ne garder que les paiements/virements du mois demandé (exclure les achats/ventes de positions).

Les transactions sont stockées dans le cache live du manager (pas en DB pour l'instant — on les fetch à la demande).

### Catégorisation

`type` est déterminé par le signe : `amount > 0` → `income`, `amount < 0` → `expense`. Pas de catégorisation avancée pour l'instant.

---

## 4. Dashboard cards

```
┌──────────────────┬──────────────────┬──────────────────┬──────────────────┐
│ Capital NET      │ Investissements  │ Cashflow du mois │ Meilleure perf.  │
│ 25 432,50 €      │ 16 932,50 €      │ +487,50 €        │ NVIDIA           │
│ +2.3% ce mois    │ P&L: +1 200 €    │ ↑ 3 200€ ↓ 2712€ │ +15.73%          │
└──────────────────┴──────────────────┴──────────────────┴──────────────────┘

[═══════════════ Courbe d'évolution du capital ═══════════════]
[1S] [1M] [3M] [1A] [Max]
```

- **Capital NET** : `GET /api/net-worth` → `total`. Le % = delta vs snapshot J-30
- **Investissements** : données du portfolio live
- **Cashflow** : `GET /api/cashflow?month=current`
- **Meilleure perf.** : inchangé
- **Courbe** : `GET /api/net-worth/history` pour le capital global

---

## Fichiers

### Créer
- `src/api/networth.py` — routes net-worth + history
- `src/api/cashflow.py` — route cashflow

### Modifier
- `src/db/models.py` — table `net_worth_snapshots`
- `src/scheduler.py` — snapshot net worth à 23h
- `src/api/router.py` — ajouter routers
- `src/connectors/trade_republic.py` — fetch `userPortfolioChartModifiedDietz` + `timelineTransactions` dans auto-fetch
- `src/connectors/woob_bank.py` — fetch transactions dans auto-fetch
- `src/manager.py` — stocker transactions dans le cache live
- `frontend/src/pages/Dashboard.tsx` — nouvelles cards + courbe
- `frontend/src/api/` — fonctions net-worth + cashflow
