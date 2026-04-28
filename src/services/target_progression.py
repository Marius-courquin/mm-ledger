from datetime import date
from sqlalchemy import select, desc
from sqlalchemy.engine import Engine

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
