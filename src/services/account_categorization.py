# src/services/account_categorization.py
from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.db.models import accounts, connectors, account_classification

CASH_CONNECTOR_TYPES = {"woob_bank", "banking"}


def categorize_accounts(engine: Engine) -> list[dict]:
    """Renvoie pour chaque compte sa catégorie cash|market et la source (auto|override)."""
    with engine.connect() as conn:
        rows = conn.execute(
            select(accounts.c.id, connectors.c.type)
            .join(connectors, accounts.c.connector_id == connectors.c.id)
        ).fetchall()
        overrides = {
            r.account_id: r.category
            for r in conn.execute(select(account_classification)).fetchall()
        }
    out = []
    for r in rows:
        if r.id in overrides:
            out.append({"account_id": r.id, "category": overrides[r.id], "auto": False})
        else:
            cat = "cash" if r.type in CASH_CONNECTOR_TYPES else "market"
            out.append({"account_id": r.id, "category": cat, "auto": True})
    return out
