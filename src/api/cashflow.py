from datetime import date
from fastapi import APIRouter, Query, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser

router = APIRouter(prefix="/api/cashflow", tags=["cashflow"])


@router.get("")
def get_cashflow(
    user: AuthUser = Depends(get_current_user),
    month: str = Query(None, description="YYYY-MM format"),
):
    """Get monthly cashflow with transactions grouped by source."""
    if not month:
        month = date.today().strftime("%Y-%m")

    # Fetch transactions from all connected workers
    all_data = deps.manager.get_user_live_data(user.id)
    sources = []
    total_income = 0.0
    total_expenses = 0.0

    for cid, data in all_data.items():
        txs = data.get("transactions", [])
        if not txs:
            continue

        # Filter to requested month
        month_txs = []
        source_income = 0.0
        source_expenses = 0.0

        for tx in txs:
            if not isinstance(tx, dict):
                continue
            tx_date = tx.get("date", "")
            # Handle both "2026-03-15" and "2026-03-15T..." formats
            if not tx_date.startswith(month):
                continue

            amount = float(tx.get("amount", 0))
            label = tx.get("label", "")

            tx_type = "income" if amount > 0 else "expense"
            if amount > 0:
                source_income += amount
            else:
                source_expenses += amount

            month_txs.append({
                "date": tx_date[:10],
                "label": label,
                "amount": amount,
                "type": tx_type,
            })

        if month_txs:
            # Sort by date desc
            month_txs.sort(key=lambda t: t["date"], reverse=True)

            # Determine source label
            source_label = cid
            # Check if it's a known connector type
            connector_health = deps.manager.get_user_health(user.id)

            sources.append({
                "source": cid,
                "label": source_label,
                "delta": source_income + source_expenses,
                "income": source_income,
                "expenses": source_expenses,
                "transactions": month_txs,
            })

            total_income += source_income
            total_expenses += source_expenses

    return {
        "month": month,
        "delta": total_income + total_expenses,
        "income": total_income,
        "expenses": total_expenses,
        "sources": sources,
    }
