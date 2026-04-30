from fastapi import APIRouter, Depends
from sqlalchemy import select

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import accounts, balance_snapshots, connectors
from src.schemas.account import AccountResponse, BalanceResponse

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.get("", response_model=list[AccountResponse])
def list_accounts(
    connector_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Liste les comptes du user. Source : live_data canonical du manager,
    fallback DB pour les comptes des connecteurs offline."""
    out: list[AccountResponse] = []
    seen_ids: set[str] = set()

    all_data = deps.manager.get_user_live_data(user.id)
    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue
        for acc in data.get("accounts", []):
            # `acc` est un CanonicalAccount (Pydantic).
            if acc.id in seen_ids:
                continue
            out.append(AccountResponse(
                id=acc.id,
                connector_id=acc.connector_id,
                connector_type=acc.connector_type,
                name=acc.label,
                kind=acc.kind,
                tax_wrapper=acc.tax_wrapper,
                currency=acc.currency,
            ))
            seen_ids.add(acc.id)

    # Fallback DB : comptes des connecteurs hors ligne ou pas encore live.
    # On JOIN avec `connectors` pour récupérer le connector_type (la colonne
    # `accounts.type` correspond au type *de compte*, pas du connecteur).
    stmt = select(
        accounts.c.id, accounts.c.connector_id, accounts.c.name,
        accounts.c.currency, connectors.c.type.label("conn_type"),
    ).select_from(
        accounts.outerjoin(connectors, accounts.c.connector_id == connectors.c.id)
    )
    if connector_id:
        stmt = stmt.where(accounts.c.connector_id == connector_id)
    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()
    for r in rows:
        if r.id in seen_ids:
            continue
        out.append(AccountResponse(
            id=r.id, connector_id=r.connector_id,
            connector_type=r.conn_type or "",
            name=r.name, kind="cash", tax_wrapper="none",
            currency=r.currency or "EUR",
        ))
        seen_ids.add(r.id)
    return out


@router.get("/{account_id}/balance", response_model=BalanceResponse)
def get_balance(account_id: str, user: AuthUser = Depends(get_current_user)):
    """Solde d'un compte. Lit le canonical en mémoire, fallback DB."""
    all_data = deps.manager.get_user_live_data(user.id)
    for _cid, data in all_data.items():
        for bal in data.get("balances", []):
            if bal.account_id == account_id:
                return BalanceResponse(
                    account_id=bal.account_id,
                    cash=float(bal.cash) if bal.cash is not None else None,
                    positions_value=float(bal.positions_value) if bal.positions_value is not None else None,
                    total_value=float(bal.total_value),
                    currency=bal.currency,
                    updated_at=bal.as_of,
                )
    # Fallback DB
    stmt = select(balance_snapshots).where(
        balance_snapshots.c.account_id == account_id
    ).order_by(balance_snapshots.c.date.desc()).limit(1)
    with deps.get_ledger(user.id).connect() as conn:
        row = conn.execute(stmt).fetchone()
    if not row:
        return BalanceResponse(account_id=account_id, total_value=0.0)
    return BalanceResponse(
        account_id=account_id,
        cash=row.cash,
        positions_value=row.positions_value,
        total_value=row.total_value or 0.0,
        currency=row.currency or "EUR",
        updated_at=row.created_at,
    )
