import time
from datetime import date, timedelta

from fastapi import APIRouter, HTTPException, Query, Response, Depends
from sqlalchemy import select, func

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import balance_snapshots

router = APIRouter(prefix="/api/snapshots", tags=["snapshots"])


@router.get("")
def list_snapshots(
    response: Response,
    account_id: str | None = None,
    limit: int = 100, offset: int = 0,
    frm: str = Query(None, alias="from"),
    to: str = None,
    user: AuthUser = Depends(get_current_user),
):
    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    filters = [balance_snapshots.c.date >= frm, balance_snapshots.c.date <= to]
    if account_id:
        filters.append(balance_snapshots.c.account_id == account_id)

    stmt = select(balance_snapshots).where(*filters).order_by(balance_snapshots.c.date).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(balance_snapshots).where(*filters)

    with deps.get_ledger(user.id).connect() as conn:
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


@router.post("/trigger", status_code=202)
def trigger_snapshot(user: AuthUser = Depends(get_current_user)):
    """Trigger a manual fetch on all connected workers."""
    health = deps.manager.get_user_health(user.id)
    triggered = []
    skipped = {}
    for cid, state in health.items():
        if state == "connected":
            deps.manager.send_command(f"{user.id}:{cid}", {"type": "fetch_balances"})
            deps.manager.send_command(f"{user.id}:{cid}", {"type": "fetch_positions"})
            triggered.append(cid)
        else:
            skipped[cid] = state
    return {"triggered": triggered, "skipped": list(skipped.keys()), "reason_skipped": skipped}


@router.post("/trigger/{connector_id}", status_code=202)
def trigger_snapshot_one(connector_id: str, user: AuthUser = Depends(get_current_user)):
    status = deps.manager.get_status(f"{user.id}:{connector_id}")
    if status["state"] != "connected":
        raise HTTPException(409, f"Worker not connected (state: {status['state']})")
    deps.manager.send_command(f"{user.id}:{connector_id}", {"type": "fetch_balances"})
    deps.manager.send_command(f"{user.id}:{connector_id}", {"type": "fetch_positions"})
    return {"triggered": connector_id}
