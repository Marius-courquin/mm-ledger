from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import accounts, balance_snapshots
from src.schemas.account import AccountResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(connector_id: str | None = None, user: AuthUser = Depends(get_current_user)):
    # First: accounts from DB
    result = []
    stmt = select(accounts)
    if connector_id:
        stmt = stmt.where(accounts.c.connector_id == connector_id)
    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()
    seen_ids = set()
    for r in rows:
        result.append(AccountResponse(id=r.id, connector_id=r.connector_id, name=r.name, type=r.type, currency=r.currency))
        seen_ids.add(r.id)

    # Second: live accounts from workers (not yet in DB)
    all_data = deps.manager.get_user_live_data(user.id)
    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue
        for acc in data.get("accounts", []):
            if isinstance(acc, dict):
                # TR format: {accounts: [{securitiesAccountNumber, cashAccountNumber, productType}]}
                acc_id = acc.get("id") or acc.get("securitiesAccountNumber") or acc.get("cashAccountNumber", "")
                if acc_id and acc_id not in seen_ids:
                    result.append(AccountResponse(
                        id=acc_id,
                        connector_id=cid,
                        name=acc.get("name") or acc.get("label") or acc.get("productType", ""),
                        type=acc.get("type") or acc.get("productType", ""),
                        currency=acc.get("currency") or acc.get("currencyId", "EUR"),
                    ))
                    seen_ids.add(acc_id)
    return result


@router.get("/{account_id}/balance")
def get_balance(account_id: str, user: AuthUser = Depends(get_current_user)):
    # Try live data first
    all_data = deps.manager.get_user_live_data(user.id)
    for cid, data in all_data.items():
        for b in data.get("balances", []):
            if isinstance(b, dict):
                return {
                    "account_id": account_id,
                    "cash": float(b.get("amount", 0)),
                    "positions_value": None,
                    "total_value": float(b.get("amount", 0)),
                    "currency": b.get("currencyId", "EUR"),
                    "updated_at": None,
                }

    # Fallback to DB
    stmt = select(balance_snapshots).where(
        balance_snapshots.c.account_id == account_id
    ).order_by(balance_snapshots.c.date.desc()).limit(1)
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return {"account_id": account_id, "cash": None, "positions_value": None, "total_value": None}
    return {
        "account_id": account_id, "cash": row.cash,
        "positions_value": row.positions_value, "total_value": row.total_value,
        "currency": row.currency, "updated_at": row.created_at,
    }
