# Design — Courbe de performance TWR (style IBKR/TR)

**Date** : 2026-04-22
**Statut** : proposé
**Auteur** : Charles (+ Claude)

## Contexte

Le dashboard affiche aujourd'hui une courbe "Capital NET" basée sur les snapshots quotidiens (`net_worth_snapshots`). Limites :

- 1 point par jour seulement, accumulé depuis le premier connect → vide la première semaine.
- Montre une valeur absolue en €, pas de lecture "rendement" directe.
- Pas de distinction entre ce qui est gagné par la perf du marché et ce qui résulte d'apports/retraits externes. Un dépôt de 1000 € fait monter la courbe de 1000 € sans que l'utilisateur ait "gagné" quoi que ce soit.

Charles veut reproduire le comportement des apps natives (IBKR mobile : "+10.61% rendement sur 1 an" avec courbe %, TR similaire) : une vraie courbe de performance qui neutralise les flux externes et révèle la perf pure des investissements.

## Objectifs

- Remplacer le chart "Capital NET" actuel du dashboard par un **composant unique avec toggle Valeur / Perf**.
- En mode **Valeur** : courbe € (équivalent fonctionnel du chart actuel).
- En mode **Perf** : courbe TWR en % sur la période, ligne horizontale à 0, couleurs semantic gain/perte adaptées à la DA existante.
- Couvrir **IBKR + TR** (reconstruction historique sur ~2 ans dès le premier connect, pas d'attente de snapshots).
- Deux échelles :
  - **Global** sur le dashboard (agrégé tous les connecteurs CTO).
  - **Par compte** sur la page détail d'un connecteur (scope restreint à ce compte).

## Non-objectifs

- Money-Weighted Return (IRR) — on reste sur du Time-Weighted.
- Benchmark vs indices (SP500, CAC40, etc.).
- Détection fine des cash flows IBKR via Flex Query (v2). En v1, on assume qu'on ne rate pas de dépôts/retraits significatifs sur la période visible.
- Courbe pour les connecteurs bancaires (`woob_bank`, `banking`) — la notion de TWR ne s'applique pas à un compte courant. Ces connecteurs restent hors du nouveau chart Perf.

## Design proposé

### 1. Méthode de calcul : Modified Dietz

Formule retenue : **Modified Dietz**, standard GIPS pour sous-périodes, bon ratio simplicité / précision face au True TWR à granularité journalière.

Pour une période `[t0, t1]` :

```
R = (V1 - V0 - ΣCF) / (V0 + Σ(CF_i × w_i))

où :
  V0            = valeur du portefeuille au début
  V1            = valeur du portefeuille à la fin
  CF_i          = cash flow externe net au jour i (positif = dépôt, négatif = retrait)
  ΣCF           = somme des cash flows externes sur la période
  w_i           = (T - t_i) / T  (pondération temporelle : part de la période durant laquelle ce cash flow a contribué)
```

Le rendement cumulé affiché dans le chart est une chaîne de `R` journaliers :
`R_cumul(t) = ∏_{i=0..t} (1 + R_i) - 1`.

### 2. Reconstruction historique par connecteur

#### 2.1 Trade Republic

- Transactions déjà disponibles via `timelineTransactions` (fetched au connect, stockées dans `live_data.transactions`).
- Champ `raw_type` distingue :
  - **Trades internes** (neutres pour TWR) : `ORDER_EXECUTED`, `TRADE_EXECUTED`, `SAVINGS_PLAN_EXECUTED`, `TRADE_CORRECTED`.
  - **Cash flows externes** : `INCOMING_TRANSFER`, `PAYMENT_INBOUND`, `PAYMENT_OUTBOUND_SEPA_DIRECT_DEBIT`, `ssp_corporate_action_invoice_cash` (à affiner à l'impl selon les event types réellement rencontrés).
  - **Perf non-trade** (compté en gain/perte) : `CREDIT` (dividendes), `INTEREST_PAYOUT_CREATED`, `ssp_tax_correction` (taxes).
- Prix historiques : nouveau fetch via WS `priceHistory` (communauté reverse) — pour chaque ISIN détenu à un moment, on pulle la série de closes quotidiens couvrant la période.

#### 2.2 IBKR

- Executions via `self._ib.reqExecutions()` — liste des fills (buy/sell) avec `execution.time`, `execution.shares`, `execution.price`, `contract.conId`.
- Prix historiques : `self._ib.reqHistoricalData(contract, durationStr="2 Y", barSizeSetting="1 day", whatToShow="TRADES")` pour chaque conId détenu à un moment. Déjà utilisé dans la branche précédente, juste à reloger.
- Cash flows externes : **approximation v1** = on suppose qu'aucun dépôt/retrait externe n'a eu lieu entre le premier trade observé et aujourd'hui. Les dividendes/intérêts IBKR sont capturés via `reqAccountUpdates` (tag `RealizedPnL`, `UnrealizedPnL`) au fil du temps ; pour l'historique reconstruit, on les considère déjà inclus dans la valeur du portefeuille à chaque close.
- v2 (hors spec) : Flex Query avec token utilisateur pour récupérer `DepositsAndWithdrawals` et `CashTransactions` officiels.

### 3. Storage — nouvelle table `portfolio_history_daily`

```sql
CREATE TABLE portfolio_history_daily (
    connector_id TEXT NOT NULL,
    account_id   TEXT NOT NULL,         -- compte IBKR U..., ou TR sec_acc_no
    date         TEXT NOT NULL,         -- ISO YYYY-MM-DD
    total_value  REAL NOT NULL,         -- en base currency (EUR)
    cash         REAL NOT NULL,
    positions_value REAL NOT NULL,
    cash_flow_external REAL DEFAULT 0,  -- net du jour (signé)
    currency     TEXT NOT NULL DEFAULT 'EUR',
    PRIMARY KEY (connector_id, account_id, date)
);
```

Populée :
- À chaque `connect` d'un worker CTO : reconstruction complète sur la période dispo (2 ans IBKR, 2 ans TR). Upsert.
- Par le scheduler quotidien (23h) : append d'un nouveau point pour aujourd'hui.

### 4. Logique pure — `src/performance.py`

Module sans dépendance connecteur (testable unitairement) :

```python
def reconstruct_timeline(
    transactions: list[dict],   # format normalisé {date, type, qty, price, symbol, amount}
    historical_prices: dict[str, list[dict]],  # {symbol: [{date, close}]}
) -> list[dict]:
    """Retourne liste triée : [{date, cash, positions_value, total_value, cash_flow_external}]"""

def compute_twr(timeline: list[dict]) -> list[dict]:
    """Chaîne de Modified Dietz journaliers → retourne [{date, cum_pct}]"""

def aggregate_timelines(timelines: list[list[dict]]) -> list[dict]:
    """Agrège plusieurs timelines de connecteurs — somme des values + somme des cash flows."""
```

### 5. API — `src/api/performance.py` (refactor)

Le fichier actuel existe mais n'est pas alimenté. On le réécrit :

- `GET /api/performance/history?period=3M&connector_id=<opt>&account_id=<opt>` :
  - Sans filtre → agrégat tous connecteurs CTO de l'utilisateur
  - Avec `connector_id` → scope 1 connecteur
  - Avec `account_id` → scope 1 compte
  - Réponse :
    ```json
    {
      "period": "3M",
      "series": [{"date": "2026-01-22", "value": 9200.0, "cum_pct": 0.0}, ...],
      "total_pct": 10.61,
      "value_now": 10166.28,
      "value_start": 9200.0,
      "currency": "EUR"
    }
    ```
- Les données viennent de `portfolio_history_daily` (filtré par user via ledger isolation).

### 6. Connecteurs — nouvelles méthodes

Ajout au contrat `ConnectorWorker` :
```python
def fetch_history_data(self) -> dict:
    """Retourne {
        'transactions': [{date, type, qty, price, symbol, amount, currency}],
        'historical_prices': {symbol: [{date, close}]},
        'current_positions': [...],
    }"""
    return {"transactions": [], "historical_prices": {}, "current_positions": []}
```

Default : vide. Implémenté par TR et IBKR, ignoré par Woob/Banking.

**Pipeline de persistance** — ajout dans la boucle `_fetch_and_emit_initial` des connecteurs qui implémentent `fetch_history_data` :

1. Worker appelle `fetch_history_data()`, émet un event `{type: "history_data", data: {...}}`.
2. Manager reconnait ce nouveau type d'event dans `collect_events`, puis délègue à un hook `_persist_history_for_worker(user_id, connector_id, data)` qui :
   - Appelle `performance.reconstruct_timeline()` (logique pure).
   - Upsert les lignes dans `portfolio_history_daily` via `deps.get_ledger(user_id)`.
3. Le scheduler quotidien (23h) appelle la même logique avec `fetch_history_data` frais pour appendre le point du jour.

Cette approche garde la logique de calcul (`reconstruct_timeline`) dans un module testable, et l'I/O DB dans le manager qui connaît déjà le user_id (via composite key `{user_id}:{connector_id}`).

### 7. Frontend

**Composant remplaçant `PerformanceChart`** : nouveau `PortfolioPerfChart.tsx`.

Props :
```ts
{
  valueSeries: { date: string; value: number }[];     // pour vue Valeur
  perfSeries: { date: string; cum_pct: number }[];    // pour vue Perf
  totalPct: number;
  valueNow: number;
  currency: string;
  periods: string[];
  activePeriod: string;
  onPeriodChange: (p: string) => void;
}
```

UI :
- Header : toggle `Valeur | Perf` à gauche, sélecteur de période à droite.
- Gros chiffre au milieu-gauche :
  - Vue Valeur : `formatCurrency(valueNow)` en gold.
  - Vue Perf : `+X.XX%` en **`var(--mm-gain)`** si positif, en **`var(--mm-loss)`** si négatif. Sous-titre : `Rendement sur {période}`.
- Courbe :
  - Vue Valeur : area chart gold (comme actuel).
  - Vue Perf : line chart, ligne 0 horizontale en dashed `border`, segments colorés dynamiquement gain/perte selon que `cum_pct ≥ 0` ou `< 0` (couleurs : `--mm-gain` pour positif, `--mm-loss` pour négatif — **pas de #4ade80/#ef4444 tailwind vifs**, on reste dans la DA du projet).

Placement :
- `frontend/src/pages/Dashboard.tsx` : remplace l'appel à `PerformanceChart` par `PortfolioPerfChart`, feed avec `/api/performance/history` (sans filtre = agrégé).
- `frontend/src/pages/AccountDetail.tsx` : remplace aussi le graphique existant `Portfolio Performance` par `PortfolioPerfChart` scopé via `connector_id=<row.connector_id>&account_id=<row.id>`.

### 8. Tests

- `tests/test_performance.py` (nouveau) — unitaires sur `reconstruct_timeline`, `compute_twr`, `aggregate_timelines` avec fixtures :
  - Pas de cash flow externe : TWR = simple return.
  - Dépôt au milieu de période : TWR neutralise le dépôt (vérifié vs ground-truth calculé à la main).
  - Multiple deposits : TWR cohérent.
  - Position qui a été totalement vendue : intégrée dans la courbe jusqu'à la vente.
- `tests/test_api_performance.py` — test du endpoint `/api/performance/history` avec fixtures DB peuplées.
- `tests/test_connector_ibkr.py` — ajout test mock `fetch_history_data()` (sans vraiment appeler reqExecutions).

### 9. Migration DB

Alembic migration pour créer la table `portfolio_history_daily` dans chaque ledger utilisateur.

## Risques et questions ouvertes

- **TR priceHistory** : l'exacte shape du message WS `priceHistory` n'est pas 100% stabilisée dans la communauté reverse ; prévoir un mode dégradé si ça fail (retomber sur 0 point pour TR, continuer à afficher IBKR agrégé).
- **Classification des cash flows TR** : la liste des `raw_type` doit être établie à l'impl par log + audit des transactions observées chez Charles. La règle par défaut "tout `INCOMING_TRANSFER` = dépôt externe" peut capturer à tort un remboursement broker. À raffiner itérativement.
- **Performance temps** : reconstruire 2 ans × 16 positions × prix historiques au connect peut prendre 30-60s. Émettre un état `building_history` côté worker pour que l'UI informe.
- **Aggregation multi-devises** : IBKR positions USD vs TR positions EUR — on convertit tout en base currency du compte via les taux existants (`_fx_to_base` côté IBKR, simple côté TR qui est déjà en EUR).
- **Snapshots existants** : on garde `net_worth_snapshots` (c'est la source de "Capital NET" global incluant les banques, différent sémantiquement). La nouvelle table `portfolio_history_daily` est spécifique aux CTO.
