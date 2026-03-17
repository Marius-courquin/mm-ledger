# Trade Republic API — Data Reference

Documentation des souscriptions WebSocket Trade Republic utilisées pour récupérer les données du portfolio.

La lib `trapi` se connecte via WebSocket à `wss://api.traderepublic.com`. Chaque requête est une "subscription" avec un type et des paramètres optionnels.

---

## Auth

```
TradeRepublicApi(phoneNumber, pin)
api.login(getDevicePin?)
```

1. Tente de réutiliser une session sauvegardée (`~/.tr_api_cookies.json`)
2. Si expirée : login avec phone+pin → push notification sur l'app TR → code 4 chiffres à saisir
3. Session persistée pour les prochains lancements

---

## Subscriptions utilisées

### `accountPairs`

Retourne tous les comptes de l'utilisateur (CTO, PEA, etc.).

```json
{
  "accounts": [
    {
      "securitiesAccountNumber": "XXXXXXXXXX",
      "cashAccountNumber": "XXXXXXXXXX",
      "productType": "DEFAULT",
      "currency": "EUR"
    },
    {
      "securitiesAccountNumber": "XXXXXXXXXX",
      "cashAccountNumber": "XXXXXXXXXX",
      "productType": "TAX_WRAPPER",
      "currency": "EUR"
    }
  ]
}
```

| `productType` | Signification |
|---|---|
| `DEFAULT` | CTO (Compte-Titres Ordinaire) |
| `TAX_WRAPPER` | PEA (Plan d'Épargne en Actions) |

Le `securitiesAccountNumber` sert d'identifiant pour requêter le portfolio par compte.

---

### `cash`

Retourne les soldes cash de tous les comptes.

```json
[
  { "accountNumber": "XXXXXXXXXX", "currencyId": "EUR", "amount": 239.04 },
  { "accountNumber": "XXXXXXXXXX", "currencyId": "EUR", "amount": 0.00 }
]
```

**Attention :** La réponse arrive parfois avec le `[` initial manquant (JSON tronqué). Il faut un fallback `JSON.parse("[" + data)`.

On associe chaque `accountNumber` au bon compte via `accountPairs.cashAccountNumber`.

---

### `compactPortfolioByType`

Retourne les positions d'un compte, groupées par catégorie.

**Paramètre :** `{ secAccNo: "XXXXXXXXXX" }`

```json
{
  "categories": [
    {
      "categoryType": "stocksAndETFs",
      "positions": [
        {
          "name": "NVIDIA",
          "isin": "US67066G1040",
          "instrumentType": "stock",
          "netSize": "3.005769",
          "averageBuyIn": "130.08",
          "derivativeInfo": null
        }
      ]
    },
    {
      "categoryType": "cryptos",
      "positions": [
        {
          "name": "Bitcoin",
          "isin": "XBT",
          "instrumentType": "crypto",
          "netSize": "0.003913",
          "averageBuyIn": "90790.07"
        }
      ]
    },
    {
      "categoryType": "privateMarkets",
      "positions": [
        {
          "name": "Private Equity",
          "instrumentType": "privateFund",
          "netSize": "0.77315",
          "averageBuyIn": "103.46"
        }
      ]
    }
  ]
}
```

| `categoryType` | Contenu |
|---|---|
| `stocksAndETFs` | Actions, ETFs, fonds |
| `cryptos` | Cryptomonnaies |
| `privateMarkets` | Private equity, fonds privés |

**Champs clés d'une position :**
- `isin` — identifiant de l'instrument (ex: `US67066G1040` pour NVIDIA, `XBT` pour Bitcoin)
- `netSize` — quantité détenue (string, peut être fractionnaire)
- `averageBuyIn` — prix moyen d'achat en EUR (string)
- `instrumentType` — `stock`, `fund`, `crypto`, `privateFund`
- `derivativeInfo` — si c'est un dérivé, contient `underlying.shortName`

---

### `ticker`

Retourne le prix live d'un instrument.

**Paramètre :** `{ id: "US67066G1040.LSX" }`

```json
{
  "last": { "price": "142.50", "time": 1773698451354 },
  "bid": { "price": "142.48" },
  "ask": { "price": "142.52" }
}
```

**Format de l'ID :**
- Stocks/ETFs : `{isin}.LSX` (Lang & Schwarz exchange)
- Crypto : `{isin}` sans suffixe (ex: `XBT`)

On utilise `last.price` en priorité, puis `bid.price` ou `ask.price` en fallback.

**Calcul P&L par position :**
```
valeur_actuelle = netSize × ticker.last.price
investi         = netSize × averageBuyIn
pnl_eur         = valeur_actuelle - investi
pnl_pct         = (pnl_eur / investi) × 100
```

---

### `aggregateHistoryLight`

Retourne l'historique de prix d'un instrument (OHLCV).

**Paramètres :** `{ id: "US67066G1040.LSX", range: "max" }`

```json
{
  "aggregates": [
    {
      "time": 1616371200000,
      "open": "570.3",
      "high": "595.0",
      "low": "540.0",
      "close": "578.2",
      "volume": 0
    }
  ]
}
```

| `range` | Période |
|---|---|
| `1d` | 1 jour |
| `5d` | 5 jours |
| `1m` | 1 mois |
| `1y` | 1 an |
| `max` | Tout l'historique |

**Notes :**
- `time` en millisecondes
- `open`/`high`/`low`/`close` sont des strings
- Même format d'ID que `ticker` (`{isin}.LSX` ou `{isin}` pour crypto)

**Utilisation pour le chart Capital :**
```
Pour chaque position de la section :
  Pour chaque point historique :
    valeur += close × netSize (quantité actuelle)
```

C'est une projection rétroactive — pas un vrai historique du portfolio.

---

### `userPortfolioChartModifiedDietz`

Performance globale calculée par TR (méthode Modified Dietz).

**Paramètre :** `{ range: "max" }`

```json
{
  "openingTime": 1717372800000,
  "expectedClosingTime": 1773698451354,
  "points": [
    {
      "timestamp": 1717372800000,
      "netValue": "60.95",
      "performance": {
        "relativeValue": "-0.0074",
        "absoluteValue": "-0.20"
      }
    }
  ],
  "currency": "EUR"
}
```

**Non utilisé dans le front** car le Modified Dietz est faussé par les dépôts/retraits — le % ne reflète pas la vraie performance des positions.

---

## Agrégation côté front

### Sections d'affichage

Les positions sont regroupées par section selon le compte et la catégorie :

| Compte (`productType`) | `categoryType` | Section affichée |
|---|---|---|
| `DEFAULT` (CTO) | `stocksAndETFs` | **CTO** |
| `DEFAULT` (CTO) | `cryptos` | **Crypto** |
| `DEFAULT` (CTO) | `privateMarkets` | **Private Equity** |
| `TAX_WRAPPER` (PEA) | `stocksAndETFs` | **PEA** |

### Valeur totale

```
totalCash       = somme des cash.amount (tous comptes)
totalPositions  = somme de (netSize × prix_live) pour chaque position
totalBalance    = totalCash + totalPositions
```

### P&L par section

```
sectionValue    = somme de (netSize × prix_live)
sectionInvested = somme de (netSize × averageBuyIn)
sectionPnl      = sectionValue - sectionInvested
sectionPnlPct   = (sectionPnl / sectionInvested) × 100
```

### Best Performer

Position avec le meilleur `(prix_live - averageBuyIn) / averageBuyIn × 100`.
