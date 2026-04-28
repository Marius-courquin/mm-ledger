from datetime import date
from sqlalchemy import select, desc
from sqlalchemy.engine import Engine
from dateutil.relativedelta import relativedelta

from src.db.models import balance_snapshots


def compute_current_value(target: dict, slices: list[dict], engine: Engine, today: date) -> float:
    """Valeur courante d'une cible.

    Type 'asset' : valeur de la position (account_id, symbol) la plus récente.
    Type 'bucket' : somme des slices (cf. Task 4).
    """
    if target["type"] == "asset":
        return _current_value_asset(target, engine)
    if target["type"] == "bucket":
        return _current_value_bucket(slices, engine)
    return 0.0


def _current_value_asset(target: dict, engine: Engine) -> float:
    stmt = (
        select(balance_snapshots.c.positions)
        .where(balance_snapshots.c.account_id == target["asset_account_id"])
        .order_by(desc(balance_snapshots.c.date))
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row or not row.positions:
        return 0.0
    for p in row.positions:
        if p.get("symbol") == target["asset_symbol"]:
            return float(p.get("value") or 0.0)
    return 0.0


def _current_value_bucket(slices: list[dict], engine: Engine) -> float:
    if not slices:
        return 0.0
    account_ids = {s["account_id"] for s in slices}
    account_values = _latest_account_values(engine, account_ids)
    total = 0.0
    for s in slices:
        acc_total = account_values.get(s["account_id"], 0.0)
        if s["allocation_kind"] == "amount":
            total += min(float(s["allocation_value"]), acc_total)
        elif s["allocation_kind"] == "percent":
            total += acc_total * float(s["allocation_value"]) / 100.0
    return total


def _latest_account_values(engine: Engine, account_ids: set[str]) -> dict[str, float]:
    """Pour chaque account_id, renvoie le total_value du snapshot le plus récent."""
    if not account_ids:
        return {}
    out: dict[str, float] = {}
    with engine.connect() as conn:
        for acc_id in account_ids:
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == acc_id)
                .order_by(desc(balance_snapshots.c.date))
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            out[acc_id] = float(row.total_value) if row and row.total_value is not None else 0.0
    return out


def compute_rate(
    target: dict,
    slices: list[dict],
    engine: Engine,
    today: date,
    lookback_months: int = 3,
) -> tuple[float, str]:
    """Renvoie (rate €/mois, source 'auto'|'override')."""
    if target.get("rate_override") is not None:
        return float(target["rate_override"]), "override"

    value_now = compute_current_value(target, slices, engine, today)
    past_date = today - relativedelta(months=lookback_months)
    value_past = _value_at(target, slices, engine, past_date)

    months_elapsed = lookback_months
    if value_past is None:
        for fallback in range(lookback_months - 1, 0, -1):
            past_date = today - relativedelta(months=fallback)
            value_past = _value_at(target, slices, engine, past_date)
            if value_past is not None:
                months_elapsed = fallback
                break
    if value_past is None or months_elapsed == 0:
        return 0.0, "auto"
    return (value_now - value_past) / months_elapsed, "auto"


def _value_at(target: dict, slices: list[dict], engine: Engine, target_date: date) -> float | None:
    """Renvoie la valeur de la cible à une date donnée. None si pas d'historique."""
    if target["type"] == "asset":
        return _value_asset_at(target, engine, target_date)
    return _value_bucket_at(slices, engine, target_date)


def _value_asset_at(target: dict, engine: Engine, target_date: date) -> float | None:
    stmt = (
        select(balance_snapshots.c.positions)
        .where(balance_snapshots.c.account_id == target["asset_account_id"])
        .where(balance_snapshots.c.date <= target_date.isoformat())
        .order_by(desc(balance_snapshots.c.date))
        .limit(1)
    )
    with engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row or not row.positions:
        return None
    for p in row.positions:
        if p.get("symbol") == target["asset_symbol"]:
            return float(p.get("value") or 0.0)
    return 0.0


def _value_bucket_at(slices: list[dict], engine: Engine, target_date: date) -> float | None:
    if not slices:
        return None
    total = 0.0
    found_any = False
    with engine.connect() as conn:
        for s in slices:
            stmt = (
                select(balance_snapshots.c.total_value)
                .where(balance_snapshots.c.account_id == s["account_id"])
                .where(balance_snapshots.c.date <= target_date.isoformat())
                .order_by(desc(balance_snapshots.c.date))
                .limit(1)
            )
            row = conn.execute(stmt).fetchone()
            if row is None:
                continue
            found_any = True
            acc_total = float(row.total_value) if row.total_value is not None else 0.0
            if s["allocation_kind"] == "amount":
                total += min(float(s["allocation_value"]), acc_total)
            else:
                total += acc_total * float(s["allocation_value"]) / 100.0
    return total if found_any else None


def compute_eta(target_amount: float, current_value: float, rate: float) -> tuple[float | None, str]:
    """Renvoie (eta_months, status)."""
    if current_value >= target_amount:
        return None, "reached"
    if rate <= 0:
        return None, "insufficient"
    return (target_amount - current_value) / rate, "ok"
