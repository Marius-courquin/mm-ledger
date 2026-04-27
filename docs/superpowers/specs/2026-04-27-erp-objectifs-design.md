# Design — Module Objectifs

**Date** : 2026-04-27
**Statut** : proposé
**Auteur** : Charles (+ Claude)
**Spec maître** : `2026-04-27-erp-master-design.md`

## Contexte

L'utilisateur veut fixer des objectifs financiers ("atteindre 5 000 € sur un ETF", "constituer 20 000 € d'apport immo") et voir sa progression. Pas de deadline : la valeur clé est "à ton rythme actuel, tu y es dans X mois".

## Objectifs

- CRUD sur les cibles.
- Deux types : cible sur actif précis (lié à une position) et bucket abstrait (composé de slices d'allocation au compte-niveau).
- Calcul de progression (% atteint, montant courant) avec courbe historique.
- Estimation "dans X mois tu y es", auto par défaut + override manuel possible.

## Non-objectifs

- Deadlines / dates cibles.
- Granularité position pour les buckets (compte-niveau uniquement).
- Versionning de l'historique des slices (v1 applique l'allocation actuelle rétroactivement).
- Notifications / alertes.

## Design proposé

### 1. Modèle de données

Deux types de cibles :

**Type A — cible sur actif** (`type='asset'`) : liée à une position spécifique (`asset_account_id`, `asset_symbol`). La valeur courante = valeur de la position. Pas de slices.

**Type B — bucket abstrait** (`type='bucket'`) : composé de N slices au compte-niveau. Chaque slice désigne un compte source et soit un montant fixe en € (typique cash), soit un pourcentage de la valeur du compte (typique CTO/PEA). Valeur courante = somme des slices évalués.

```sql
CREATE TABLE targets (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT NOT NULL,
    type               TEXT NOT NULL CHECK(type IN ('asset', 'bucket')),
    target_amount      REAL NOT NULL,
    -- type='asset' uniquement :
    asset_account_id   TEXT,           -- account_id de la position
    asset_symbol       TEXT,           -- ISIN ou symbol
    -- override manuel du rythme (€/mois). NULL = auto depuis snapshots.
    rate_override      REAL,
    archived           INTEGER NOT NULL DEFAULT 0,
    created_at         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE target_slices (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    target_id          INTEGER NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
    account_id         TEXT NOT NULL,
    allocation_kind    TEXT NOT NULL CHECK(allocation_kind IN ('amount', 'percent')),
    allocation_value   REAL NOT NULL          -- € si 'amount', 0..100 si 'percent'
);

CREATE INDEX idx_target_slices_target ON target_slices(target_id);
```

### 2. Calcul de la progression

**Valeur courante :**

- Type A : valeur de la position `(asset_account_id, asset_symbol)` lue depuis `positions`. Si la position n'existe pas (vendu, jamais détenu), valeur = 0.
- Type B : pour chaque slice :
  - `kind='amount'` → contribution = `allocation_value` (capped à la valeur courante du compte).
  - `kind='percent'` → contribution = `allocation_value/100 × valeur_compte_courante`.
  - Valeur courante du compte lue depuis le solde le plus récent (snapshots / balances selon le connecteur).

**Courbe historique** :

- On reconstruit en appliquant l'allocation actuelle rétroactivement aux snapshots.
- Type A : valeur historique d'une position spécifique. Sources disponibles dans le ledger :
  - `balance_snapshots.positions` (JSON, par compte/jour) — contient le breakdown des positions, à parser pour extraire la valeur de `(account_id, symbol)` à chaque date.
  - `portfolio_history_daily.total_value` (par compte/jour) — pas de breakdown par position, donc inutilisable seul.
  - **Stratégie v1** : parser `balance_snapshots.positions` pour reconstruire la série journalière de la position. Si la position n'apparaît pas dans le JSON pour un jour donné, valeur 0 ce jour-là (cohérent : pas détenue). Si aucun snapshot n'existe pour cette position, courbe plate à la valeur courante (fallback).
- Type B : pour chaque jour J et chaque slice, on prend la valeur historique du compte source ce jour-là (depuis `balance_snapshots.total_value` ou `portfolio_history_daily.total_value` selon le connecteur) et on applique la slice (montant fixe inchangé, pourcentage appliqué à la valeur historique).

**Rythme :**

- Auto (`rate_override IS NULL`) : pente sur les N derniers mois (config : 3 mois par défaut).
  - `rate = (valeur_aujourd_hui - valeur_il_y_a_3_mois) / 3` (€/mois).
  - Si historique < 3 mois, on utilise la fenêtre disponible (≥ 1 mois) ; sinon `rate = 0`.
- Manuel (`rate_override IS NOT NULL`) : valeur en €/mois saisie par l'utilisateur.

**ETA :**

- Si `rate > 0` et `valeur_courante < target_amount` :
  `eta_months = (target_amount - valeur_courante) / rate`.
- Si `rate ≤ 0` et `valeur_courante < target_amount` : "rythme insuffisant".
- Si `valeur_courante ≥ target_amount` : "atteint".

### 3. Endpoints API

Préfixe : `/api/targets` (FastAPI, JWT cookie comme partout).

```
GET    /api/targets                              # liste (filtre archived)
POST   /api/targets                              # création
GET    /api/targets/{id}                         # détail (incl. slices)
PUT    /api/targets/{id}                         # update (name, target_amount, rate_override, archived)
DELETE /api/targets/{id}                         # suppression dure
POST   /api/targets/{id}/slices                  # ajout slice (type='bucket' uniquement)
PUT    /api/targets/{id}/slices/{slice_id}       # update slice
DELETE /api/targets/{id}/slices/{slice_id}       # suppression slice
GET    /api/targets/{id}/progression             # snapshot courant + historique (jours, valeurs) + rythme + ETA
```

Schémas Pydantic dans `src/schemas/targets.py`.

### 4. UI

**Page `/objectifs`**
- Liste des cibles sous forme de cards (titre, type badge, montant cible, barre de progression, montant courant, ETA).
- Bouton "Nouvelle cible" → modale avec choix type (asset / bucket).
- Toggle "Afficher archivées".

**Page détail `/objectifs/{id}`**
- Header : nom, montant cible, montant courant, progression %, ETA.
- Courbe historique (Recharts LineChart, couleur `--mm-gain` si rythme positif, sinon neutre).
- Input rythme override (placeholder = rythme auto calculé).
- Section slices (type=bucket) avec ajout/edit/remove inline. Chaque ligne = sélecteur compte + radio (€ / %) + input valeur.
- Section position (type=asset) en lecture seule (account + symbol, pas modifiable après création).

**Card "Objectifs" sur le Dashboard**
- Top 3 cibles non archivées par progression % décroissante.
- Lien "Voir tout" → page `/objectifs`.

### 5. Backend

- `src/api/targets.py` — routes.
- `src/schemas/targets.py` — Pydantic.
- `src/db/models.py` — ajout des `Table("targets", ...)` et `Table("target_slices", ...)` (style Core, cohérent avec les tables existantes).
- `src/services/target_progression.py` — calculs progression, courbe historique, rythme (fonctions pures).

### 6. Tests

`tests/test_api_targets.py` :
- CRUD basique sur target type asset.
- CRUD basique sur target type bucket avec 2 slices.
- Type A : progression depuis position fixturée.
- Type B : slices % et €, calcul de la valeur courante.
- Reconstruction historique sur snapshots fixturés.
- Rythme auto sur historique > 3 mois et historique < 3 mois.
- Rythme override.
- ETA "atteint", ETA "insuffisant", ETA en mois.
- Cascade delete des slices à la suppression de la target.

## Notes d'implémentation

- Les slices d'un bucket peuvent référencer un compte qui n'existe pas (compte fermé, etc.). Dans ce cas, la slice contribue 0 et l'UI affiche un warning sur la cible.
- L'unicité (target_id, account_id) n'est PAS imposée — l'utilisateur peut techniquement avoir deux slices sur le même compte (pas recommandé mais pas bloqué).
