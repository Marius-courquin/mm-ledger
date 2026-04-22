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
) -> list[dict]:
    """Rebuild daily portfolio state from transactions + historical prices.

    Returns : list[{date, cash, positions_value, total_value, cash_flow_external}] sorted ASC.
    """
    if start_date > end_date:
        return []

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

        positions_value = 0.0
        day_prices = price_by_date.get(d, {})
        for symbol, qty in positions.items():
            price = day_prices.get(symbol)
            if price is None:
                price = _last_known_close(historical_prices.get(symbol, []), d)
            if price is not None:
                positions_value += qty * price

        result.append({
            "date": d,
            "cash": round(cash, 4),
            "positions_value": round(positions_value, 4),
            "total_value": round(cash + positions_value, 4),
            "cash_flow_external": round(daily_external_cf, 4),
        })

    return result


def _last_known_close(bars: list[dict], as_of: str) -> float | None:
    candidates = [float(b["close"]) for b in bars if b["date"] <= as_of]
    return candidates[-1] if candidates else None


def compute_twr(timeline: list[dict]) -> list[dict]:
    """Chaîne les rendements journaliers Modified Dietz.

    Formule par jour i :
        r_i = (V_i - V_{i-1} - CF_i) / V_{i-1}

    Rendement cumulé : ∏ (1 + r_i) − 1, exprimé en pourcentage.
    """
    if not timeline:
        return []

    curve = [{"date": timeline[0]["date"], "cum_pct": 0.0}]
    cumulative_factor = 1.0

    for i in range(1, len(timeline)):
        prev_v = timeline[i - 1]["total_value"]
        curr_v = timeline[i]["total_value"]
        cf = timeline[i].get("cash_flow_external", 0.0)

        if prev_v <= 0:
            curve.append({"date": timeline[i]["date"], "cum_pct": round((cumulative_factor - 1) * 100, 4)})
            continue

        daily_return = (curr_v - prev_v - cf) / prev_v
        cumulative_factor *= (1.0 + daily_return)
        curve.append({
            "date": timeline[i]["date"],
            "cum_pct": round((cumulative_factor - 1) * 100, 4),
        })

    return curve
