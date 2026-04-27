# Design — Module Projection

**Date** : 2026-04-27
**Statut** : proposé
**Auteur** : Charles (+ Claude)
**Spec maître** : `2026-04-27-erp-master-design.md`

## Contexte

L'utilisateur veut projeter son patrimoine sur 5/10/20/30 ans pour anticiper son évolution avec des hypothèses simples (taux de rendement, apport mensuel). Style Finary.

## Objectifs

- Page Projection avec sliders/inputs ajustables :
  - Taux annuel cash + taux annuel marché.
  - Apport mensuel cash + apport mensuel marché.
  - Horizon (5 / 10 / 20 / 30 ans).
- Capital de départ lu depuis l'état courant des comptes (cash vs marché classifié auto, override possible).
- Mensualités de prêts intégrées comme sortie auto sur le cash.
- Une courbe en aire empilée (cash + marché).

## Non-objectifs

- Events one-shot (prime, achat immo, etc.).
- Scénarios multiples sauvegardés.
- Bandes pessimiste/optimiste, Monte Carlo.
- Per-account rate.
- Auto-recalibrage du taux depuis l'historique réel (l'utilisateur décide ses taux).

## Design proposé

### 1. Classification cash vs marché

Règle de classification automatique d'un compte :

- **Cash** : tout compte dont le `connector_type` est `woob_bank` ou `banking`.
- **Marché** : tout compte dont le `connector_type` est `trade_republic`, `ibkr`, ou tout autre futur connecteur courtier.

Si un courtier expose un compte cash pur (rare), v1 → classé marché par défaut. L'utilisateur peut overrider via la table `account_classification`.

### 2. Modèle de données

```sql
-- Settings globaux de projection (single row)
CREATE TABLE projection_settings (
    id                          INTEGER PRIMARY KEY CHECK (id = 1),
    cash_annual_rate            REAL NOT NULL DEFAULT 0.02,    -- 2 %/an
    market_annual_rate          REAL NOT NULL DEFAULT 0.05,    -- 5 %/an
    cash_monthly_contribution   REAL NOT NULL DEFAULT 0,
    market_monthly_contribution REAL NOT NULL DEFAULT 0,
    horizon_years               INTEGER NOT NULL DEFAULT 10
);

-- Override de classification compte par compte (optionnel)
CREATE TABLE account_classification (
    account_id      TEXT PRIMARY KEY,
    category        TEXT NOT NULL CHECK(category IN ('cash', 'market'))
);
```

Le row unique de `projection_settings` est upserté à la première lecture (init en migration ou lazy à `GET /api/projection/settings`).

### 3. Calcul de la projection

Boucle mois par mois sur `horizon_years × 12` mois.

```python
cash_t = cash_initial
market_t = market_initial
loan_monthly = sum(loan.monthly_payment for loan in active_loans)

cash_monthly_rate   = (1 + cash_annual_rate)   ** (1/12) - 1
market_monthly_rate = (1 + market_annual_rate) ** (1/12) - 1

points = []
for month in range(horizon_years * 12):
    cash_t   = cash_t   * (1 + cash_monthly_rate)   + cash_monthly_contribution - loan_monthly
    market_t = market_t * (1 + market_monthly_rate) + market_monthly_contribution
    points.append({
        "month_offset": month + 1,
        "cash":   cash_t,
        "market": market_t,
        "total":  cash_t + market_t,
    })
```

Notes :
- Si `cash_t` devient négatif (mensualités prêts > apport + intérêts), on l'affiche tel quel — c'est un signal pour l'utilisateur, pas un cas d'erreur.
- Les mensualités prêts sont déduites de manière constante sur tout l'horizon. Quand un prêt arrive à échéance pendant l'horizon, **v1 ne réduit PAS la mensualité globale** au-delà de sa fin. À la place : on calcule pour chaque mois t la somme des mensualités des prêts encore actifs ce mois-là (`loan.end_date > today + t mois`). Plus honnête, peu de complexité ajoutée.

### 4. Endpoints API

Préfixe : `/api/projection`.

```
GET    /api/projection/settings              # settings + classification courante des comptes (auto + override)
PUT    /api/projection/settings              # update settings (taux, apports, horizon)
GET    /api/projection/compute               # capital de départ + liste de points mensuels
POST   /api/projection/account-override      # POST {account_id, category} pour overrider la classification
DELETE /api/projection/account-override/{account_id}  # retirer un override
```

`GET /api/projection/compute` réponse :

```json
{
  "starting_state": {
    "cash":   12345.67,
    "market": 56789.01,
    "loan_monthly": 1234.56
  },
  "settings": { ... },
  "points": [
    {"month_offset": 1, "cash": ..., "market": ..., "total": ..., "loan_monthly_active": 1234.56},
    ...
  ]
}
```

### 5. UI

**Page `/projection`**
- Bandeau supérieur : capital de départ (cash + marché + total).
- Panneau "Hypothèses" :
  - Slider taux cash (0–10 %, pas 0,1 %).
  - Slider taux marché (0–15 %, pas 0,1 %).
  - Input apport mensuel cash (€).
  - Input apport mensuel marché (€).
  - Select horizon (5 / 10 / 20 / 30 ans).
  - Note "Mensualités prêts intégrées : X €/mois".
- Courbe : Recharts AreaChart, stack `cash` + `market`. Couleurs DA, axe Y €, axe X années.
- Cards en bas : "À 5 ans : X €", "À 10 ans : Y €", "À 20 ans : Z €", "À 30 ans : W €" (toujours affichées, on calcule jusqu'au max 30 ans).
- Lien discret "Classification des comptes" → modale listant les comptes avec leur classification courante et un toggle override.

**Card "Projection" sur le Dashboard**
- Capital projeté à `horizon_years` (chiffre simple).
- Lien vers la page.

### 6. Backend

- `src/api/projection.py` — routes.
- `src/schemas/projection.py` — Pydantic.
- `src/db/models.py` — ajout des `Table("projection_settings", ...)` et `Table("account_classification", ...)` (style Core).
- `src/services/projection_calc.py` — `compute_projection(settings, accounts, loans, today) -> ProjectionResult` (fonction pure).
- `src/services/account_categorization.py` — classification cash/marché.

### 7. Tests

`tests/test_api_projection.py` :
- Compute avec settings par défaut + capital nul → courbe à 0.
- Compute avec capital + taux = 0 + apports = 0 → courbe plate.
- Compute avec capital + taux marché 5 % + apport 100 €/mois → vérification math sur un point connu.
- Mensualités prêts correctement déduites du cash.
- Mensualité réduite quand un prêt arrive à terme dans l'horizon.
- Cas cash négatif (sortie > entrée) : la projection sort sans erreur.
- Override classification : un compte courtier reclassé cash bascule bien dans le `cash_initial`.

## Notes d'implémentation

- Décisions par défaut sur taux : 2 % cash / 5 % marché. Ce sont des valeurs raisonnables pour la France 2026, l'utilisateur ajuste.
- L'horizon max calculé est toujours 30 ans côté backend pour permettre les cards "À X ans" même quand `horizon_years` est plus court côté UI. La courbe affichée respecte `horizon_years`.
- `loan_monthly_active` calculé par mois : permet à l'UI d'afficher éventuellement un trait pointillé "fin du dernier prêt" sur le chart (v1.1).
