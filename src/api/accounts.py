from fastapi import APIRouter
from sqlalchemy import select

from src.api import deps
from src.db.models import accounts, balance_snapshots
from src.schemas.account import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(connector_id: str | None = None):
    stmt = select(accounts)
    if connector_id:
        stmt = stmt.where(accounts.c.connector_id == connector_id)
    with deps.db_engine.connect() as conn:
        rows = conn.execute(stmt).fetchall()
    return [AccountResponse(id=r.id, connector_id=r.connector_id, name=r.name, type=r.type, currency=r.currency) for r in rows]


@router.get("/{account_id}/balance")
def get_balance(account_id: str):
    stmt = select(balance_snapshots).where(
        balance_snapshots.c.account_id == account_id
    ).order_by(balance_snapshots.c.date.desc()).limit(1)
    with deps.db_engine.connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return {"account_id": account_id, "cash": None, "positions_value": None, "total_value": None}
    return {
        "account_id": account_id, "cash": row.cash,
        "positions_value": row.positions_value, "total_value": row.total_value,
        "currency": row.currency, "updated_at": row.created_at,
    }
