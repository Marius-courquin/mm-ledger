from datetime import date, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import balance_snapshots

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    response: Response,
    account_id: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [balance_snapshots.c.date >= frm, balance_snapshots.c.date <= to]
    if account_id:
        filters.append(balance_snapshots.c.account_id == account_id)

    stmt = select(balance_snapshots).where(*filters).order_by(balance_snapshots.c.date).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(balance_snapshots).where(*filters)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "account_id": r.account_id, "date": r.date,
            "cash": r.cash, "positions_value": r.positions_value,
            "total_value": r.total_value, "currency": r.currency,
            "positions": r.positions,
        }
        for r in rows
    ]
