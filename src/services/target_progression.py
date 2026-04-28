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
    # implémenté en Task 4
    return 0.0
