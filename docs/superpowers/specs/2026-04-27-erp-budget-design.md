# Design — Module Budget

**Date** : 2026-04-27
**Statut** : proposé
**Auteur** : Charles (+ Claude)
**Spec maître** : `2026-04-27-erp-master-design.md`

## Contexte

L'utilisateur veut un budget mensuel déclaratif simple : revenus, charges fixes, charges variables, et le calcul de la capacité d'investissement résiduelle. Pas de catégorisation auto des transactions bancaires en v1.

## Objectifs

- L'utilisateur crée ses propres **sections** (libres, ex. "Salaires", "Logement", "Transport", "Loisirs") avec un type (revenu / charge fixe / charge variable).
- Chaque section contient des **items** (libellé + montant mensuel, ex. "Loyer" / 800 €).
- Section "Prêts" virtuelle auto-générée depuis le module Prêts (un item par prêt actif, lecture seule).
- Capacité d'investissement = total revenus − total charges (incluant prêts).
- Bouton "Appliquer cette capacité comme apport mensuel projection" — modale demandant la répartition cash / marché.

## Non-objectifs

- Catégorisation auto des transactions bancaires.
- Comparaison réel vs prévu (multi-mois, alertes).
- Règles de ventilation auto (ex. "X % du salaire → marché").
- Historique des budgets / versionning (un seul budget courant en v1).
- Plusieurs budgets parallèles (utile pour scénarios) — pas en v1.

## Design proposé

### 1. Modèle de données

```sql
CREATE TABLE budget_sections (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    section_type    TEXT NOT NULL CHECK(section_type IN ('income', 'fixed_expense', 'variable_expense')),
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE budget_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    section_id      INTEGER NOT NULL REFERENCES budget_sections(id) ON DELETE CASCADE,
    label           TEXT NOT NULL,
    amount          REAL NOT NULL,
    position        INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_budget_items_section ON budget_items(section_id);
```

Pas de table pour la section virtuelle "Prêts" : générée à la lecture.

### 2. Section "Prêts" virtuelle

Injectée à chaque appel `GET /api/budget` :

```python
{
  "id": "virtual:loans",
  "name": "Prêts",
  "section_type": "fixed_expense",
  "is_virtual": True,
  "position": -1,    # toujours en tête de fixed_expense
  "items": [
    {
      "id": f"virtual:loan:{loan.id}",
      "label": loan.name,
      "amount": loan.monthly_payment,
      "is_virtual": True
    }
    for loan in active_loans
  ]
}
```

Côté UI : section affichée avec icône cadenas. Édition désactivée. Lien "Modifier dans Prêts" ouvre `/prets`.

Côté API : tous les endpoints d'édition refusent les ids préfixés `virtual:` (400 Bad Request avec message clair).

### 3. Calcul

```
total_income        = somme(items des sections section_type='income')
total_fixed_user    = somme(items des sections section_type='fixed_expense' non virtuelles)
total_loans         = somme(monthly_payment des prêts actifs)
total_fixed         = total_fixed_user + total_loans
total_variable      = somme(items des sections section_type='variable_expense')
total_expense       = total_fixed + total_variable
investment_capacity = total_income - total_expense
```

Si `investment_capacity < 0` : on affiche le chiffre négatif, pas d'erreur.

### 4. Endpoints API

Préfixe : `/api/budget`.

```
GET    /api/budget                              # sections (réelles + virtuelle prêts) + items + totaux
POST   /api/budget/sections                     # création section (name, section_type, position)
PUT    /api/budget/sections/{id}                # update (name, section_type, position)
DELETE /api/budget/sections/{id}                # suppression (cascade items)
POST   /api/budget/sections/{id}/items          # ajout item
PUT    /api/budget/items/{id}                   # update item (label, amount, position)
DELETE /api/budget/items/{id}                   # suppression item
POST   /api/budget/apply-to-projection          # body {cash_share: 0..1, market_share: 0..1}
                                                # met à jour projection_settings.cash/market_monthly_contribution
```

Endpoints d'édition refusent les ids `virtual:*` avec 400.

`GET /api/budget` réponse :

```json
{
  "sections": [
    {"id": 1, "name": "Salaires", "section_type": "income", "position": 0,
     "is_virtual": false, "items": [...]},
    {"id": "virtual:loans", "name": "Prêts", "section_type": "fixed_expense",
     "position": -1, "is_virtual": true, "items": [...]},
    {"id": 2, "name": "Logement", "section_type": "fixed_expense", "position": 0,
     "is_virtual": false, "items": [...]},
    ...
  ],
  "totals": {
    "income": 3500.0,
    "fixed_expense": 1934.56,
    "variable_expense": 600.0,
    "expense": 2534.56,
    "investment_capacity": 965.44
  }
}
```

### 5. UI

**Page `/budget`**
- Layout 3 colonnes (responsive : accordéon mobile) : Revenus | Charges fixes | Charges variables.
- Dans chaque colonne :
  - Liste des sections (avec drag handle pour position).
  - Bouton "+ Section" en pied de colonne.
- Dans chaque section :
  - Header : nom (éditable), bouton "+", bouton "supprimer" (sauf virtuelle).
  - Liste des items (label + montant, éditables inline ou modale).
  - Total de section en pied.
- Section virtuelle "Prêts" : affichée en tête de la colonne "Charges fixes", icône cadenas, bouton "Modifier dans Prêts".
- Footer sticky en bas de page :
  - Total revenus | Total charges | **Capacité d'investissement = X €/mois**.
  - Bouton "Appliquer à la projection" → modale "comment répartir 965 € entre cash et marché ?" (deux sliders qui se complètent à 100 %, default 0/100).

**Card "Budget" sur le Dashboard**
- Capacité d'investissement courante.
- Lien vers la page.

### 6. Backend

- `src/api/budget.py` — routes.
- `src/schemas/budget.py` — Pydantic (avec serializer custom pour ids virtuels).
- `src/db/models.py` — ajout des `Table("budget_sections", ...)` et `Table("budget_items", ...)` (style Core).
- `src/services/budget_compose.py` — `compose_budget(db, loans) -> BudgetView` qui injecte la section virtuelle.

### 7. Tests

`tests/test_api_budget.py` :
- CRUD sections + items.
- Section virtuelle Prêts apparaît avec les prêts actifs (et seulement ceux-là).
- Édition d'un id virtuel → 400.
- Totaux cohérents (incl. prêts).
- `apply-to-projection` met à jour `projection_settings`.
- Capacité négative s'affiche sans erreur.

## Notes d'implémentation

- À la migration initiale, on crée des sections "starter" pour démarrer (cohérent avec un onboarding à venir) :
  - Revenus : "Salaires" (vide).
  - Charges fixes : "Logement" (vide), "Abonnements" (vide).
  - Charges variables : "Alimentation" (vide), "Loisirs" (vide).
  - L'utilisateur peut tout supprimer / réordonner / renommer.
- Drag-and-drop position : utiliser `react-dnd` ou simple "↑ ↓" en v1 (plus simple, moins de deps).
