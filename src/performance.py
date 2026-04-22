"""Calcul de performance (TWR Modified Dietz) — logique pure, sans I/O.

Entrées : transactions normalisées + prix historiques (tout déjà en base currency).
Sortie : timeline journalière + courbe cumulée %."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

TxKind = Literal["buy", "sell", "deposit", "withdrawal", "dividend", "fee", "interest"]

# Types de tx classés comme cash flow externe (apport ou retrait — neutralisés dans TWR).
EXTERNAL_KINDS: set[str] = {"deposit", "withdrawal"}


@dataclass
class TxEvent:
    """Transaction normalisée dans la base currency du compte.

    amount : impact signé sur le cash (dépôt +, retrait -, buy -, sell +, dividende +, fee -).
    qty : pour buy/sell uniquement, signé (achat > 0, vente < 0).
    """
    date: str
    kind: TxKind
    symbol: str | None = None
    qty: float = 0.0
    price: float = 0.0
    amount: float = 0.0


def _daterange(start: str, end: str) -> list[str]:
    d0 = date.fromisoformat(start)
    d1 = date.fromisoformat(end)
    return [(d0 + timedelta(days=i)).isoformat() for i in range((d1 - d0).days + 1)]


def reconstruct_timeline(
    transactions: list[TxEvent],
    historical_prices: dict[str, list[dict]],
    start_date: str,
    end_date: str,
    current_cash: float | None = None,
    current_positions: dict[str, float] | None = None,
) -> list[dict]:
    """Rebuild daily portfolio state.

    Deux modes :
    - **forward** (défaut) : démarre de cash=0, positions={} au start_date et applique
      les txs. Biais : rate les positions héritées avant la fenêtre.
    - **backward** (si current_cash OU current_positions fourni) : part de l'état
      actuel connu (end_date) et défait les txs jour par jour. Reflète la réalité
      même si l'historique des trades ne couvre pas toute la fenêtre."""
    if start_date > end_date:
        return []
    if current_cash is not None or current_positions is not None:
        return _reconstruct_backwards(
            transactions, historical_prices, start_date, end_date,
            current_cash or 0.0, current_positions or {},
        )
    return _reconstruct_forwards(transactions, historical_prices, start_date, end_date)


def _reconstruct_forwards(
    transactions: list[TxEvent],
    historical_prices: dict[str, list[dict]],
    start_date: str,
    end_date: str,
) -> list[dict]:
    price_by_date: dict[str, dict[str, float]] = {}
    for symbol, bars in historical_prices.items():
        for bar in bars:
            price_by_date.setdefault(bar["date"], {})[symbol] = float(bar["close"])

    txs_by_date: dict[str, list[TxEvent]] = {}
    for tx in transactions:
        txs_by_date.setdefault(tx.date, []).append(tx)

    cash = 0.0
    positions: dict[str, float] = {}
    result = []

    for d in _daterange(start_date, end_date):
        daily_external_cf = 0.0
        for tx in txs_by_date.get(d, []):
            cash += tx.amount
            if tx.kind in EXTERNAL_KINDS:
                daily_external_cf += tx.amount
            if tx.kind in ("buy", "sell") and tx.symbol:
                positions[tx.symbol] = positions.get(tx.symbol, 0.0) + tx.qty
                if abs(positions[tx.symbol]) < 1e-9:
                    positions.pop(tx.symbol, None)

        positions_value = _compute_positions_value(positions, price_by_date.get(d, {}), historical_prices, d)
        result.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(cash + positions_value, 4),
            "cash_flow_external": round(daily_external_cf, 4),
        })

    return result


def _reconstruct_backwards(
    transactions: list[TxEvent],
    historical_prices: dict[str, list[dict]],
    start_date: str,
    end_date: str,
    current_cash: float,
    current_positions: dict[str, float],
) -> list[dict]:
    price_by_date: dict[str, dict[str, float]] = {}
    for symbol, bars in historical_prices.items():
        for bar in bars:
            price_by_date.setdefault(bar["date"], {})[symbol] = float(bar["close"])

    txs_by_date: dict[str, list[TxEvent]] = {}
    for tx in transactions:
        txs_by_date.setdefault(tx.date, []).append(tx)

    all_dates = _daterange(start_date, end_date)
    state_by_date: dict[str, tuple[float, dict[str, float]]] = {
        all_dates[-1]: (current_cash, dict(current_positions)),
    }
    for i in range(len(all_dates) - 1, 0, -1):
        today = all_dates[i]
        yesterday = all_dates[i - 1]
        cash, positions = state_by_date[today]
        cash = float(cash)
        positions = dict(positions)
        for tx in txs_by_date.get(today, []):
            cash -= tx.amount
            if tx.kind in ("buy", "sell") and tx.symbol:
                positions[tx.symbol] = positions.get(tx.symbol, 0.0) - tx.qty
                if abs(positions[tx.symbol]) < 1e-9:
                    positions.pop(tx.symbol, None)
        state_by_date[yesterday] = (cash, positions)

    result = []
    for d in all_dates:
        cash, positions = state_by_date[d]
        daily_external_cf = sum(
            tx.amount for tx in txs_by_date.get(d, []) if tx.kind in EXTERNAL_KINDS
        )
        positions_value = _compute_positions_value(positions, price_by_date.get(d, {}), historical_prices, d)
        result.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(cash + positions_value, 4),
            "cash_flow_external": round(daily_external_cf, 4),
        })
    return result


def _compute_positions_value(
    positions: dict[str, float],
    day_prices: dict[str, float],
    historical_prices: dict[str, list[dict]],
    as_of: str,
) -> float:
    total = 0.0
    for symbol, qty in positions.items():
        price = day_prices.get(symbol)
        if price is None:
            price = _last_known_close(historical_prices.get(symbol, []), as_of)
        if price is not None:
            total += qty * price
    return total


def _last_known_close(bars: list[dict], as_of: str) -> float | None:
    candidates = [float(b["close"]) for b in bars if b["date"] <= as_of]
    return candidates[-1] if candidates else None


def compute_twr(timeline: list[dict]) -> list[dict]:
    """Rendement cumulé en % — chaîne des rendements journaliers TWR avec anchor
    à la première valeur "matérielle" + safeguard anti-explosion.

    Pour chaque jour t > anchor :
        r_t = (V_t - V_{t-1} - CF_t) / V_{t-1}    (clamped to [-99%, +1000%])
        cum_pct(t) = (∏(1 + r_i) − 1) × 100

    Anchor = première valeur ≥ MATERIAL_THRESHOLD. Avant anchor, cum_pct = 0.
    Si prev_v descend sous le threshold (comptes quasi-vidés), on re-ancre au point
    courant sans compounder ce jour-là → évite les +188955% causés par division
    par ~0 (bug observé chez Charles : courbe All écrasée à cause d'un V_start=0.01€).
    """
    if not timeline:
        return []

    MATERIAL_THRESHOLD = 10.0
    MAX_DAILY = 10.0   # +1000%
    MIN_DAILY = -0.99  # -99%

    start_idx = -1
    for i, pt in enumerate(timeline):
        if pt["total_value"] >= MATERIAL_THRESHOLD:
            start_idx = i
            break
    if start_idx < 0:
        return [{"date": pt["date"], "cum_pct": 0.0} for pt in timeline]

    curve = [{"date": pt["date"], "cum_pct": 0.0} for pt in timeline[:start_idx + 1]]
    cumulative_factor = 1.0
    prev_v = timeline[start_idx]["total_value"]

    for i in range(start_idx + 1, len(timeline)):
        pt = timeline[i]
        curr_v = pt["total_value"]
        cf = pt.get("cash_flow_external", 0.0)

        if prev_v < MATERIAL_THRESHOLD:
            # Réancrage : on ne compound pas si la base est instable (≈ 0 / négative)
            prev_v = curr_v
            curve.append({"date": pt["date"], "cum_pct": round((cumulative_factor - 1) * 100, 4)})
            continue

        daily_return = (curr_v - prev_v - cf) / prev_v
        if daily_return > MAX_DAILY:
            daily_return = MAX_DAILY
        elif daily_return < MIN_DAILY:
            daily_return = MIN_DAILY
        cumulative_factor *= (1.0 + daily_return)
        prev_v = curr_v
        curve.append({"date": pt["date"], "cum_pct": round((cumulative_factor - 1) * 100, 4)})

    return curve


def aggregate_timelines(timelines: list[list[dict]]) -> list[dict]:
    """Fusionne plusieurs timelines (1 par connecteur) en sommant les champs numériques
    par date. Avant le premier point d'une timeline donnée, elle contribue à 0."""
    if not timelines:
        return []
    all_dates = sorted({pt["date"] for t in timelines for pt in t})
    if not all_dates:
        return []

    per_timeline_by_date = [
        {pt["date"]: pt for pt in t} for t in timelines
    ]

    merged = []
    for d in all_dates:
        cash = 0.0
        positions_value = 0.0
        total_value = 0.0
        cf_ext = 0.0
        for by_date in per_timeline_by_date:
            pt = by_date.get(d)
            if pt is None:
                continue
            cash += pt["cash"]
            positions_value += pt["positions_value"]
            total_value += pt["total_value"]
            cf_ext += pt.get("cash_flow_external", 0.0)
        merged.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(total_value, 4),
            "cash_flow_external": round(cf_ext, 4),
        })
    return merged
