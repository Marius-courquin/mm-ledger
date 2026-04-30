# Design — Couche de normalisation canonical (Comptes, Soldes, Positions) + auto-détection des prêts

**Date** : 2026-04-30
**Statut** : proposé
**Auteur** : Charles (+ Claude)

## Contexte

Au fil des features récentes (banking, IBKR, perf chart, ERP), chaque connecteur émet sa donnée brute et chaque consommateur (API `/api/accounts`, dashboard, scheduler, snapshots) re-fait son propre mapping. Conséquences observées sur la prod locale :

- Le PEA Trade Republic s'affiche `TAX_WRAPPER` et à `0,00 €` dans **Comptes connectés** (label `PRODUCT_LABELS` appliqué uniquement au cash, pas aux comptes ; balance match cassé entre `securitiesAccountNumber` côté account et `cashAccountNumber` côté cash).
- Les positions Trade Republic en **crypto** et **private equity** sortent du portefeuille mais ne remontent pas dans la valorisation par compte.
- Les comptes prêts retournés par Woob (ex: `Vcc - Pret Jeune Standard`, solde négatif) apparaissent comme un compte bancaire ordinaire, sans lien avec le module Prêts. À chaque sync ils ré-apparaissent tels quels — pas de moyen de capter qu'un remboursement a eu lieu.

Symptôme commun : pas de schéma canonical pour `Account` / `Balance` / `Position`. Chaque connecteur a son shape, chaque consommateur fait du `acc.get("name") or acc.get("label") or acc.get("productType")` avec des fallbacks ad-hoc.

## Objectifs

1. Définir un **schéma canonical** typé pour Comptes, Soldes, Positions (Pydantic).
2. Implémenter une **couche de normalisation** par connecteur, branchée dans le `ConnectorManager` à la réception des events. Le `live_data` ne contient plus que du canonical.
3. Refonder les API `/api/accounts`, `/api/accounts/{id}/balance`, `/api/portfolio/positions` sur ce schéma. Le front consomme du canonical, plus de mapping côté UI.
4. **Auto-détecter les comptes de type prêt** depuis Woob et Enable Banking, les exposer comme **candidats** côté module Prêts, permettre de les lier à un prêt existant (ou en créer un nouveau préremplit) — avec **idempotence** garantie via une table de lien.
5. Quand un prêt est lié à un compte bancaire, **prendre le solde bancaire comme source de vérité** pour `amount_remaining` (avec fallback calendaire si le sync est trop ancien).

## Non-objectifs

- Refonte de la persistance ledger (les tables `accounts`, `balance_snapshots`, `positions` restent — on canonicalise la couche live + API, pas le stockage).
- Refonte du worker process model.
- Conversion FX multi-devises (on reste EUR-centric — un champ `currency` est exposé pour le futur).
- Détection de prêts par **pattern de nom** ("prêt", "crédit", "Vcc"…) — un faux positif sur un "Compte épargne prêt habitat" est plus coûteux qu'un faux négatif. On se base uniquement sur les types fournis par les APIs (`cash_account_type` Woob, `cashAccountType` PSD2).
- Tableau d'amortissement : le module Prêts reste déclaratif côté capital initial / mensualité / durée. Le solde bancaire ne fait que **remplacer** le calcul de `amount_remaining` quand il est dispo.

## Design

### 1. Schéma canonical

`src/normalizers/types.py` (Pydantic) :

```python
from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

AccountKind = Literal["cash", "securities", "liability"]
TaxWrapper = Literal[
    "none", "cto", "pea", "pea_pme", "per", "av",
    "livret_a", "livret_jeune", "ldds", "lep", "cel", "pel",
]
AssetClass = Literal["equity", "etf", "bond", "crypto", "private", "other"]

class CanonicalAccount(BaseModel):
    id: str                      # ID stable cross-sync (cf. § "Stable IDs")
    connector_id: str
    connector_type: str          # "trade_republic" | "ibkr" | "woob_bank" | "banking"
    label: str                   # User-facing : "PEA", "CTO", "Livret A", "Compte Prêt Jeune"
    kind: AccountKind
    tax_wrapper: TaxWrapper = "none"
    currency: str = "EUR"

class CanonicalBalance(BaseModel):
    account_id: str
    cash: Decimal | None = None              # Pour kind=securities, cash dispo sur le compte espèces lié
    positions_value: Decimal | None = None   # Somme des Position.value pour cet account (None si non applicable)
    total_value: Decimal                     # cash + positions_value ; pour liability : solde dû (négatif ou positif selon convention — voir § Convention)
    currency: str = "EUR"
    as_of: datetime

class CanonicalPosition(BaseModel):
    account_id: str
    symbol: str
    isin: str | None = None
    name: str
    quantity: Decimal
    average_price: Decimal | None = None
    current_price: Decimal | None = None
    value: Decimal                           # quantity * current_price (devise du compte)
    asset_class: AssetClass
    currency: str = "EUR"
```

**Convention `total_value` pour `kind=liability`** : on stocke la dette en valeur **négative** (ex : `-3800.00`). C'est cohérent avec ce que rend Woob aujourd'hui et ça permet aux sommes "patrimoine net" de fonctionner sans logique spéciale (somme des `total_value` = capital net).

### 2. Stable IDs

L'idempotence du lien prêt ↔ compte dépend d'un `id` canonical stable cross-sync.

| Connecteur | `id` canonical |
|---|---|
| `trade_republic` | `securitiesAccountNumber` (compte titres) ou `cashAccountNumber` (compte cash) — préfixé `tr:` |
| `ibkr` | `accountId` IBKR (ex: `U24281721`) |
| `woob_bank` | `account.id` Woob (stable) — préfixé `woob:{backend}:` pour éviter collisions cross-banque |
| `banking` | `account.uid` Enable Banking (stable PSD2) — préfixé `eb:` |

Ces préfixes empêchent les collisions cross-connecteur dans la table `loan_account_link`. Migration : si des `account_id` non préfixés existent déjà en base (`balance_snapshots`, `positions`), on ajoute une migration Alembic qui préfixe rétroactivement (best effort, sinon on laisse — le live data reprendra avec les nouveaux IDs).

### 3. Architecture — invocation dans le manager

```
src/normalizers/
  __init__.py        # get_normalizer(connector_type) -> Normalizer (registry)
  types.py           # Pydantic CanonicalAccount/Balance/Position + enums
  base.py            # Normalizer ABC
  trade_republic.py  # TRNormalizer
  ibkr.py            # IBKRNormalizer
  woob_bank.py       # WoobNormalizer
  enable_banking.py  # BankingNormalizer (pour connector_type="banking")
```

`base.Normalizer` :
```python
class Normalizer(ABC):
    @abstractmethod
    def normalize_accounts(self, raw: Any, connector_id: str) -> list[CanonicalAccount]: ...
    @abstractmethod
    def normalize_balances(self, raw: Any, accounts: list[CanonicalAccount]) -> list[CanonicalBalance]: ...
    @abstractmethod
    def normalize_positions(self, raw: Any, accounts: list[CanonicalAccount]) -> list[CanonicalPosition]: ...
```

`base.balances` reçoit les `accounts` déjà normalisés pour pouvoir matcher cash↔securities (cf. bug PEA TR : c'est exactement ce match qui était cassé).

**Wiring dans `ConnectorManager`** : dans la boucle qui draine `event_queue`, avant le stockage en `live_data` :

```python
def _handle_event(self, key: str, event: dict):
    connector_type = self._workers[key].connector_type
    normalizer = get_normalizer(connector_type)
    bucket = self.live_data.setdefault(key, {})

    if event["type"] == "accounts":
        bucket["accounts"] = normalizer.normalize_accounts(event["data"], connector_id=key)
    elif event["type"] == "balances":
        bucket["balances"] = normalizer.normalize_balances(event["data"], bucket.get("accounts", []))
    elif event["type"] == "positions":
        bucket["positions"] = normalizer.normalize_positions(event["data"], bucket.get("accounts", []))
    else:
        bucket[event["type"]] = event["data"]   # transactions, status, errors : passe-plat
```

**Invariant** : `bucket["accounts"]`, `bucket["balances"]`, `bucket["positions"]` sont **toujours** des `list[Canonical*]` ou absents. Le raw n'est plus stocké que dans les logs.

### 4. Règles de normalisation par connecteur

#### 4.1 Trade Republic

Source : `accountPairs` (`{accounts: [{securitiesAccountNumber, cashAccountNumber, productType}]}`), `availableCash` (par `accountNumber`), `compactPortfolioByType` (catégories).

```python
PRODUCT_TYPE_TO_CANONICAL = {
    # productType TR -> (label, kind, tax_wrapper)
    "DEFAULT":        ("CTO", "securities", "cto"),
    "TAX_WRAPPER":    ("PEA", "securities", "pea"),
    "PEA":            ("PEA", "securities", "pea"),  # garde-fou
    "CRYPTO":         ("Crypto", "securities", "none"),       # kind=securities car positions cryptos
    "PRIVATE_EQUITY": ("Private Equity", "securities", "none"),
}

CATEGORY_TO_ASSET_CLASS = {
    "stocks": "equity", "etfs": "etf", "bonds": "bond",
    "cryptos": "crypto", "privateMarkets": "private",
    "derivatives": "other",
}
```

- `normalize_accounts` : 1 compte canonical par entrée TR `accounts[]`, `id = "tr:{securitiesAccountNumber or cashAccountNumber}"`.
- `normalize_balances` : pour chaque cash entry, trouver l'account canonical dont l'id matche **soit** sec soit cash account no (les deux préfixes `tr:` candidats). Sommer le `current_value` des positions de ce compte pour `positions_value`. `total_value = cash + positions_value`. **Fix bug PEA**.
- `normalize_positions` : itérer sur `categories[].positions[]`, mapper `categoryType` → `asset_class`. Pour `private` (pas de prix), `value` = `netSize` ou `0` (best effort), `current_price = None`. **Fix crypto/PE absents de la valo**.

#### 4.2 IBKR

Source : `ib_async` `accountSummary()` + `positions()`.

- `id = "ibkr:{account_id}"`, `kind = "securities"`, `tax_wrapper = "cto"` (IBKR n'expose pas de wrapper FR).
- Positions : `asset_class` dérivé de `contract.secType` (`STK`→equity, `ETF`→etf, `BOND`→bond, `CRYPTO`→crypto, autres→other).

#### 4.3 Woob (`woob_bank`)

Source : `Account` Woob avec `cash_account_type`, `type`, `balance`.

```python
WOOB_TYPE_TO_KIND = {
    Account.TYPE_CHECKING: "cash",
    Account.TYPE_SAVINGS:  "cash",
    Account.TYPE_DEPOSIT:  "cash",
    Account.TYPE_LOAN:     "liability",   # ← signal primaire pour la détection prêt
    Account.TYPE_MARKET:   "securities",
    Account.TYPE_PEA:      "securities",
    Account.TYPE_LIFE_INSURANCE: "securities",
    # ... fallback "cash"
}

WOOB_TYPE_TO_TAX_WRAPPER = {
    Account.TYPE_PEA: "pea",
    Account.TYPE_LIFE_INSURANCE: "av",
    Account.TYPE_PERP: "per",
    # Livret A / Jeune / LDDS : déduit du label (regex strict, sinon "none")
}
```

- `id = "woob:{backend}:{account.id}"`, `label = account.label`.
- Pour `kind=liability` : `total_value = -abs(balance)` (convention dette négative).
- Livret A / Livret Jeune : on tente une regex sur le label (`r"\bLivret\s+A\b"`, `r"\bLivret\s+Jeune\b"`) pour assigner `tax_wrapper`. Si pas de match → `tax_wrapper="none"`. Pas de fallback ouvert.

#### 4.4 Enable Banking (`banking`)

Source : PSD2 `cashAccountType` (codes ISO 20022 : `CACC`, `SVGS`, `LOAN`, `CARD`, …).

```python
PSD2_TYPE_TO_KIND = {
    "CACC": "cash",       # Current
    "SVGS": "cash",       # Savings
    "LOAN": "liability",
    "CARD": "liability",  # Carte de crédit revolving
    "MOMA": "cash",       # Money Market
    # ... fallback "cash"
}
```

- `id = "eb:{account.uid}"`, `label = account.name or account.product`.

### 5. Détection prêts + lien (β + b)

#### 5.1 Table de lien

Ajout dans le ledger user :

```sql
CREATE TABLE loan_account_link (
    account_id   TEXT PRIMARY KEY,                    -- canonical Account.id
    loan_id      INTEGER NULL REFERENCES loans(id) ON DELETE SET NULL,
    ignored      INTEGER NOT NULL DEFAULT 0,
    last_balance REAL NULL,                           -- dernier solde vu (cache)
    last_seen_at TEXT NULL,                           -- ISO datetime du dernier sync
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_loan_account_link_loan ON loan_account_link(loan_id);
```

États possibles :
- `loan_id IS NULL AND ignored=0` → **candidat** affiché côté UI.
- `loan_id IS NOT NULL` → **lié** (masqué des candidats, prêt utilise le solde bancaire).
- `ignored=1` → **ignoré** (n'apparaît plus en candidat).

#### 5.2 API

Ajouts sur `/api/loans` :

```
GET    /api/loans/candidates              # liabilities détectées non liées non ignorées
POST   /api/loans/{loan_id}/link          # body: {account_id} → crée/update loan_account_link
DELETE /api/loans/{loan_id}/link          # détache (loan_id → NULL, ignored reste 0)
POST   /api/loans/candidates/{account_id}/ignore   # ignored=1
DELETE /api/loans/candidates/{account_id}/ignore   # ignored=0 (réapparaît en candidat)
POST   /api/loans/from-account            # body: {account_id, name, monthly_payment, total_months, start_date, loan_type, initial_capital}
                                          #   → crée loan + crée lien dans même transaction
```

`GET /api/loans/candidates` retourne :
```json
[
  {
    "account_id": "woob:bp:abc123",
    "label": "Vcc - Pret Jeune Standard M CHARLES BOURNONVILLE",
    "balance": -4000.00,
    "currency": "EUR",
    "connector_type": "woob_bank",
    "as_of": "2026-04-30T08:14:00Z"
  }
]
```

#### 5.3 Source de vérité `amount_remaining`

Refacto de `src/services/loan_calc.py::compute_loan_state` :

```python
def compute_loan_state(
    loan: dict,
    today: date,
    linked_balance: Decimal | None = None,
    balance_as_of: datetime | None = None,
) -> dict:
    # ... calculs calendaires existants (months_paid, months_remaining_calendar, end_date, ...)

    use_bank = (
        linked_balance is not None
        and balance_as_of is not None
        and (datetime.utcnow() - balance_as_of).days < 7
    )

    if use_bank:
        amount_remaining = abs(linked_balance)
        months_remaining = (
            int(round(amount_remaining / loan["monthly_payment"]))
            if loan["monthly_payment"] > 0 else 0
        )
        amount_source = "bank"
    else:
        amount_remaining = monthly_payment * months_remaining_calendar
        months_remaining = months_remaining_calendar
        amount_source = "calendar"

    return {..., "amount_remaining": amount_remaining,
            "months_remaining": months_remaining,
            "amount_source": amount_source}
```

`amount_source` est exposé dans `LoanResponse` → l'UI peut afficher "calculé / synchronisé bancaire" et la fraîcheur du sync.

`/api/loans/{id}` et `/api/loans` lisent le solde bancaire via `loan_account_link` jointé au `live_data` du manager (ou au cache `last_balance` si le worker n'est pas connecté en ce moment, avec `last_seen_at` pour la fraîcheur).

#### 5.4 UI

**Page `/prets`** :
- Section "Candidats détectés" en haut, conditionnelle (cachée si zéro candidat). Pour chaque ligne :
  - `[{label}]  {balance €}  {connector_type badge}`
  - Boutons : **`Lier à un prêt existant`** (modale select dans `loans` actifs) / **`Créer depuis ce compte`** (ouvre la modale de création préremplie : `name`=label, `initial_capital`=|balance|, reste à compléter) / **`Ignorer`**.
- Cards de prêts existants : si `linked_account_id`, badge "*Lié à : {label} (banque)*" + ligne discrète "Solde synchronisé : 3 800 €" (ou "Calcul calendaire : 3 800 €" si fallback).

**Module Budget** : la section virtuelle Prêts utilise toujours `monthly_payment` (déclaratif) — non affectée.

### 6. Refonte des API existantes

| Endpoint | Avant | Après |
|---|---|---|
| `GET /api/accounts` | Mix DB + live, mapping ad-hoc | Lit le canonical depuis `live_data` du manager, fallback DB. Retourne `list[CanonicalAccount]`. |
| `GET /api/accounts/{id}/balance` | Match cassé sec/cash, fallback `balance_snapshots` | Lit `live_data["balances"]`, match direct sur `account_id` canonical. Retourne `CanonicalBalance`. |
| `GET /api/portfolio/positions` | Format hétérogène par connecteur | Concatène `live_data["positions"]` de tous les connecteurs du user. Retourne `list[CanonicalPosition]`. |

**Persistance** : les tables `accounts`, `balance_snapshots`, `positions` du ledger sont écrites **depuis le canonical** (sauf migration). Les schémas SQL n'ont pas besoin de changer (les colonnes existantes sont un sous-ensemble du canonical) — on ajoute juste les colonnes manquantes (`kind`, `tax_wrapper`) en migrations Alembic.

### 7. Front

- `frontend/src/lib/types.ts` : ajouter `Account.kind`, `Account.tax_wrapper`, `Position.asset_class`. Plus aucune logique de mapping côté UI.
- `Dashboard.tsx` Comptes connectés : affiche `account.label` directement (plus de calcul de subtitle hardcodé sur `connector.type`).
- Couleur d'icône par `kind` (cash → vert, securities → violet, liability → rouge).
- `/prets` : nouvelle section Candidats + badges de lien, comme décrit en § 5.4.

### 8. Tests

`tests/normalizers/` :
- `test_trade_republic.py` : fixtures de raw `accountPairs` + `availableCash` + `compactPortfolioByType` (PEA + CTO avec crypto + PE) → assert canonical : 2 comptes, balances correctes (PEA non plus 0€), positions inclusives crypto + PE.
- `test_woob_bank.py` : fixtures avec compte courant + Livret A + Livret Jeune + prêt → assert `kind` et `tax_wrapper` corrects, prêt avec `total_value < 0`.
- `test_enable_banking.py` : fixtures PSD2 (CACC, SVGS, LOAN) → idem.
- `test_ibkr.py` : fixture mock `ib_async` → canonical.

`tests/test_api_loans.py` : ajouter cas
- `GET /api/loans/candidates` retourne les liabilities non liées non ignorées, exclut les liées et ignorées.
- `POST /api/loans/{id}/link` + sync ultérieur : `amount_remaining` reflète le nouveau solde bancaire (mocker `live_data`).
- Fraîcheur > 7 jours → fallback calendaire (`amount_source="calendar"`).
- `POST /api/loans/from-account` : crée loan + lien atomiquement.

`tests/test_manager.py` : assert que `live_data` contient bien du `CanonicalAccount` (Pydantic model) après dispatch d'un event raw.

### 9. Migration / déploiement

1. Schéma canonical + infra normalizers (PR 1).
2. Wiring manager + tests (PR 2). À ce stade, les API actuelles tournent sur le canonical mais retournent encore l'ancien shape (couche de compat dans les routes).
3. Refonte API + front (PR 3). Breaking change minor sur `/api/accounts` (champs renommés) → bump versionnage interne, le front est livré dans le même PR.
4. Normalizer Trade Republic (PR 4) → résout PEA + crypto/PE.
5. Normalizer Woob (PR 5) → kind=liability disponible.
6. Normalizer Enable Banking (PR 6).
7. Normalizer IBKR (PR 7).
8. Module candidats prêts + UI (PR 8) → résout l'auto-détection.
9. Refonte `compute_loan_state` avec linked_balance (PR 9).

Chaque PR : tests verts, déployable individuellement.

### 10. Risques / points ouverts

- **Stable IDs cross-sync** : si un connecteur banking change ses `uid` après refresh OAuth (pas censé, mais à vérifier sur Enable Banking), le lien casse → un compte ignoré pourrait re-apparaître. Mitigation : monitoring / log d'alerte si plus de N comptes "nouveaux" sur un sync donné.
- **Devise non-EUR** : on stocke `currency` mais la somme `cash + positions_value` suppose même devise. Pour multi-devise (futur), prévoir conversion FX au point de canonicalisation. Pas dans ce scope.
- **Convention `total_value` négatif pour liability** : impacte la card "Capital net" du dashboard. Vérifier que `Σ total_value` reste cohérent (= patrimoine net incluant dettes).
- **Performance** : la normalisation à chaque event est O(n) sur n petit (≤ 50 comptes par user). Coût négligeable.

## Décisions tranchées

| Sujet | Choix |
|---|---|
| Couche d'abstraction | (B) Normalizers dédiés `src/normalizers/{type}.py` |
| Scope | (B2) Comptes + Soldes + Positions |
| Schéma `Account` | (iii) `kind` + `tax_wrapper` orthogonaux |
| Invocation | (1) Dans `ConnectorManager._handle_event` |
| Auto-détection prêts | (β) Candidats + lien manuel via `loan_account_link` |
| Source `amount_remaining` | (b) Solde bancaire si dispo + frais (< 7 jours), fallback calendaire |
| Détection `kind=liability` | Uniquement via type API (`cash_account_type` Woob, `cashAccountType` PSD2). Pas de regex sur le nom. |

## Liens

- Spec module Prêts : `docs/superpowers/specs/2026-04-27-erp-prets-design.md`
- Spec maître ERP : `docs/superpowers/specs/2026-04-27-erp-master-design.md`
- Spec persistance session : `docs/superpowers/specs/2026-04-29-session-persistence-design.md`
