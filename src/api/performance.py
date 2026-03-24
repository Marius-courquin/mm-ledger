from datetime import date, timedelta

from fastapi import APIRouter, Query, Response
from sqlalchemy import select, func

from src.api import deps
from src.db.models import performance

router = APIRouter(prefix="/api/performance", tags=["performance"])


@router.get("")
def list_performance(
    response: Response,
    connector_id: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [performance.c.period_start >= frm, performance.c.period_start <= to]
    if connector_id:
        filters.append(performance.c.connector_id == connector_id)

    stmt = select(performance).where(*filters).order_by(performance.c.period_start).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(performance).where(*filters)

    with deps.db_engine.connect() as conn:
        total = conn.execute(count_stmt).scalar()
        rows = conn.execute(stmt).fetchall()

    response.headers["X-Total-Count"] = str(total)
    return [
        {
            "connector_id": r.connector_id,
            "period_start": r.period_start, "period_end": r.period_end,
            "total_value": r.total_value, "total_invested": r.total_invested,
            "pnl": r.pnl, "pnl_pct": r.pnl_pct, "breakdown": r.breakdown,
        }
        for r in rows
    ]
