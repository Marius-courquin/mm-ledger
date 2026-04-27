# Design — ERP de gestion patrimoniale (vision et architecture)

**Date** : 2026-04-27
**Statut** : proposé
**Auteur** : Charles (+ Claude)

## Contexte

mm-ledger agrège aujourd'hui les comptes (CTO, PEA, banques) et affiche le capital, les positions et la performance. La prochaine étape : transformer mm-ledger en ERP de gestion patrimoniale personnelle, qui couvre 4 nouveaux modules :

1. **Objectifs** — fixer des cibles (5 K€ sur un ETF, 20 K€ d'apport immo) et suivre la progression.
2. **Prêts** — déclarer ses crédits et voir la durée restante / le restant à payer.
3. **Projection** — projeter le capital à 5/10/20 ans avec hypothèses de rendement et apports.
4. **Budget** — répartir le salaire entre charges et capacité d'investissement.

Vision : "tu peux tout prédire, tout calculer".

## Principes directeurs

- **Au plus simple, mais bien fait** — chaque module v1 doit être vraiment utilisable avec un minimum de friction. Pas de Monte Carlo, pas d'amortissement complexe, pas de catégorisation auto des transactions. Les options simples par défaut, l'option "puissante" plus tard.
- **Cohérence avec le reste de l'app** — frontend français, JWT auth existante, multi-user strict (tout dans `data/users/{id}/ledger.db`), DA `--mm-gain` / `--mm-loss`.
- **Modularité** — chaque module est autonome côté UI et data, mais partage une cohérence inter-modules (mensualités prêts → Budget, capacité Budget → Projection, positions → Objectifs).

## Architecture des modules

```
                       [Positions / Snapshots existants]
                                  │
             ┌────────────────────┼─────────────────────┐
             ▼                    ▼                     ▼
        [Objectifs]          [Projection]           [Budget]
                                  ▲                     │
                                  │                     ▼
                              [Prêts] ──mensualités────┘
```

- **Objectifs** : lit positions + snapshots, autonome.
- **Prêts** : autonome, expose la liste des mensualités actives.
- **Budget** : importe les mensualités prêts comme charges fixes (section virtuelle) ; expose la capacité d'investissement.
- **Projection** : lit l'état actuel des comptes (cash + marché), consomme les mensualités prêts en sortie, prend la capacité Budget en suggestion d'apport (via un bouton).

## Data models partagés

Toutes les nouvelles tables vivent dans le ledger SQLCipher de l'utilisateur (`data/users/{id}/ledger.db`). Pas de `user_id` dans les tables — l'isolation se fait par fichier de base.

Tables introduites :
- `targets`, `target_slices` (module Objectifs)
- `loans` (module Prêts)
- `projection_settings`, `account_classification` (module Projection)
- `budget_sections`, `budget_items` (module Budget)

Les FK pointent uniquement vers les tables existantes (`positions`, `accounts`) quand pertinent.

## Création des tables

Le projet utilise `metadata.create_all(engine)` au démarrage (cf. `src/db/engine.py`), pas de migrations Alembic actives. Ajouter une table revient donc à la déclarer dans `src/db/models.py` — elle sera créée au prochain démarrage si elle n'existe pas.

Ordre des additions à `models.py` :

1. `targets`, `target_slices` (Objectifs)
2. `loans` (Prêts)
3. `projection_settings`, `account_classification` (Projection)
4. `budget_sections`, `budget_items` (Budget)

Pour les modifications de schéma (alter column, etc.) sur tables existantes : pas de cas en v1 puisqu'on n'ajoute que des nouvelles tables. Si besoin plus tard, prévoir une stratégie (drop+recreate en dev, vraies migrations en prod).

## Ordre d'implémentation

Selon la priorité de Charles :

1. **Objectifs** (autonome, débloque la motivation)
2. **Prêts** (autonome, simple)
3. **Projection** (consomme positions + prêts)
4. **Budget** (consomme prêts, alimente Projection)

Chaque module a son propre spec détaillé et son propre plan d'implémentation. Pas de big-bang : on merge module par module.

## Conventions UI

- Une page dédiée par module : `/objectifs`, `/prets`, `/projection`, `/budget`.
- Chaque module a une "card résumé" sur le Dashboard (chiffre clé + lien vers la page).
- Couleurs gain/perte = `--mm-gain` / `--mm-loss` (DA existante).
- Tout en français.
- Recharts pour les graphes (déjà utilisé).
- HeroUI pour les composants (déjà utilisé).

## Tests

Chaque module a sa propre suite `tests/test_api_<module>.py`. Tests d'intégration croisée (mensualité prêt → budget, prêts + budget → projection) dans `tests/test_erp_integration.py` après les 4 modules.

## Non-objectifs (v1, tous modules)

- Catégorisation auto des transactions bancaires.
- Tableau d'amortissement de prêts, calcul du capital restant dû exact.
- Monte Carlo / scénarios multiples sauvegardés pour la projection.
- Events one-shot dans la projection.
- Deadlines sur les objectifs.
- Granularité position pour les buckets d'objectifs.
- Versionning de l'historique des slices d'objectifs.
- Comparaison réel vs prévu sur le budget.
- Notifications / alertes.

Ces points sont laissés ouverts pour une v2 module par module.

## Spec individuels

- `2026-04-27-erp-objectifs-design.md`
- `2026-04-27-erp-prets-design.md`
- `2026-04-27-erp-projection-design.md`
- `2026-04-27-erp-budget-design.md`
