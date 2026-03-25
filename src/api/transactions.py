from datetime import date, timedelta

from fastapi import APIRouter, Query, Response, Depends
from sqlalchemy import select, func

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import transactions

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.get("")
def list_transactions(
    response: Response,
    account_id: str | None = None,
    type: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
    user: AuthUser = Depends(get_current_user),
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [transactions.c.date >= frm, transactions.c.date <= to]
    if account_id:
        filters.append(transactions.c.account_id == account_id)
    if type:
        filters.append(transactions.c.type == type)

    stmt = select(transactions).where(*filters).order_by(transactions.c.date.desc()).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(transactions).where(*filters)

    with deps.get_ledger(user.id).connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "id": r.id, "account_id": r.account_id, "date": r.date,
            "type": r.type, "label": r.label, "amount": r.amount,
            "currency": r.currency, "instrument": r.instrument,
            "quantity": r.quantity, "price": r.price,
        }
        for r in rows
    ]
