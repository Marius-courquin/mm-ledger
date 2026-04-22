from datetime import date, timedelta
from fastapi import APIRouter, Query, Depends
from sqlalchemy import select

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.db.models import portfolio_history_daily
from src.performance import compute_twr, aggregate_timelines

router = APIRouter(prefix="/api/performance", tags=["performance"])

PERIOD_DAYS = {"1W": 7, "1M": 30, "3M": 90, "1Y": 365, "All": None}


def _period_start(period: str) -> str | None:
    days = PERIOD_DAYS.get(period, 90)
    if days is None:
        return None
    return (date.today() - timedelta(days=days)).isoformat()


@router.get("/history")
def get_history(
    period: str = Query("3M"),
    connector_id: str | None = None,
    account_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Courbe Valeur + courbe Perf TWR sur la période, scoped user (+ optionnel connector/account)."""
    since = _period_start(period)
    stmt = select(portfolio_history_daily).order_by(
        portfolio_history_daily.c.connector_id,
        portfolio_history_daily.c.account_id,
        portfolio_history_daily.c.date,
    )
    if since:
        stmt = stmt.where(portfolio_history_daily.c.date >= since)
    if connector_id:
        stmt = stmt.where(portfolio_history_daily.c.connector_id == connector_id)
    if account_id:
        stmt = stmt.where(portfolio_history_daily.c.account_id == account_id)

    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()

    # Group par (connector_id, account_id) → list de timelines
    grouped: dict[tuple[str, str], list[dict]] = {}
    for r in rows:
        grouped.setdefault((r.connector_id, r.account_id), []).append({
            "date": r.date,
            "total_value": r.total_value,
            "cash": r.cash,
            "positions_value": r.positions_value,
            "cash_flow_external": r.cash_flow_external,
        })
    timelines = list(grouped.values())
    merged = aggregate_timelines(timelines) if timelines else []

    perf_curve = compute_twr(merged)
    total_pct = perf_curve[-1]["cum_pct"] if perf_curve else 0.0
    value_now = merged[-1]["total_value"] if merged else 0.0
    value_start = merged[0]["total_value"] if merged else 0.0
    currency = rows[0].currency if rows else "EUR"

    perf_by_date = {p["date"]: p["cum_pct"] for p in perf_curve}
    series = [
        {"date": pt["date"], "value": pt["total_value"], "cum_pct": perf_by_date.get(pt["date"], 0.0)}
        for pt in merged
    ]
    return {
        "period": period,
        "series": series,
        "total_pct": total_pct,
        "value_now": value_now,
        "value_start": value_start,
        "currency": currency,
    }
