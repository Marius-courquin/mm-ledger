# Design — Module Prêts

**Date** : 2026-04-27
**Statut** : proposé
**Auteur** : Charles (+ Claude)
**Spec maître** : `2026-04-27-erp-master-design.md`

## Contexte

L'utilisateur veut suivre ses crédits (immo, conso, auto, autres) sans se prendre la tête : combien il reste de mensualités, combien à payer encore, date de fin. Pas de calcul d'amortissement (pas de taux saisis), juste du suivi déclaratif.

## Objectifs

- CRUD sur les prêts.
- Calcul calendaire simple : mensualités restantes, date de fin, montant restant à payer (= mensualité × restantes).
- Tous types de prêts (immo / conso / auto / autre).
- Lien vers Budget : la mensualité de chaque prêt est exposée comme charge fixe (consommé par le module Budget via une section virtuelle).

## Non-objectifs

- Tableau d'amortissement.
- Capital restant dû exact (nécessite le taux).
- Remboursement anticipé en feature spéciale (l'utilisateur édite la durée à la main si besoin).
- Taux variable / révisable.
- Tracking individuel des paiements (déclaratif uniquement, pas de marquage "mensualité X payée").

## Design proposé

### 1. Modèle de données

```sql
CREATE TABLE loans (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    loan_type       TEXT NOT NULL CHECK(loan_type IN ('immo', 'conso', 'auto', 'other')),
    initial_capital REAL NOT NULL,           -- capital emprunté à l'origine (€)
    monthly_payment REAL NOT NULL,           -- mensualité (€)
    total_months    INTEGER NOT NULL,        -- durée totale en mois
    start_date      TEXT NOT NULL,           -- date première mensualité (ISO YYYY-MM-DD)
    archived        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);
```

### 2. Calculs (côté serveur)

Pour chaque prêt :

- `end_date = start_date + total_months mois` (ajout calendaire mois par mois, pas en jours).
- `months_paid = nb mois pleins entre start_date et today`, clampé à `[0, total_months]`.
- `months_remaining = total_months − months_paid`.
- `amount_remaining = monthly_payment × months_remaining`.
- `progress_pct = months_paid / total_months × 100`.
- `is_active = months_remaining > 0 AND archived = 0`.

Cas limites :
- `start_date` dans le futur → `months_paid = 0`, `progress_pct = 0`.
- `today >= end_date` → `months_paid = total_months`, `months_remaining = 0`, `is_active = False`.

### 3. Endpoints API

Préfixe : `/api/loans`.

```
GET    /api/loans                  # liste (filtre archived)
POST   /api/loans                  # création
GET    /api/loans/{id}             # détail (avec calculs)
PUT    /api/loans/{id}             # update (tous champs sauf id, created_at)
DELETE /api/loans/{id}             # suppression dure
GET    /api/loans/summary          # somme mensualités actives, somme amount_remaining, end_date max
```

Le module Budget consomme `GET /api/loans` (filtré sur `is_active`) pour générer sa section virtuelle "Prêts".

### 4. UI

**Page `/prets`**
- Table responsive : nom, type (badge coloré), mensualité, restantes / total, date fin, restant total à payer, progression % (barre).
- Bouton "Nouveau prêt" → modale form (nom, type, capital initial, mensualité, durée mois, date début).
- Edit via icône crayon → modale (mêmes champs).
- Suppression via icône poubelle (confirmation).
- Toggle "Afficher archivés".

**Card "Prêts" sur le Dashboard**
- Somme mensualités actives / mois.
- Date de fin la plus lointaine.
- Lien "Voir tout" → page `/prets`.

### 5. Backend

- `src/api/loans.py` — routes.
- `src/schemas/loans.py` — Pydantic (LoanCreate, LoanUpdate, LoanRead avec calculs).
- `src/db/models.py` — ajout du `Table("loans", ...)` (style Core).
- `src/services/loan_calc.py` — fonctions pures `compute_loan_state(loan, today) -> dict`.

### 6. Tests

`tests/test_api_loans.py` :
- CRUD basique.
- Calculs calendaires : `start_date` passé, futur, exactement aujourd'hui.
- `months_remaining = 0` quand `today >= end_date`.
- `progress_pct = 100` à terme.
- Edge case : `total_months = 1`.
- Endpoint `summary` agrège correctement, ignore les archivés et les terminés.

## Notes d'implémentation

- L'addition `start_date + N mois` doit être faite avec `dateutil.relativedelta` (pas une approximation à 30 jours) pour éviter les dérives.
- Tous les montants en `Decimal` côté Python pour éviter les flottants ; conversion REAL côté SQLite (acceptable pour de l'affichage, pas de la compta).
- Pas d'index : nb de prêts attendu par user < 10, scan séquentiel OK.
