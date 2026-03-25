from datetime import date, timedelta
from fastapi import APIRouter, Query, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser

router = APIRouter(prefix="/api/cashflow", tags=["cashflow"])

PERIOD_DAYS = {"1W": 7, "1M": 30, "3M": 90, "6M": 180, "1Y": 365}

# TR event types that are NOT cashflow (investment operations)
TR_INVESTMENT_TYPES = {
    "TRADE_INVOICE", "SAVINGS_PLAN_EXECUTED", "SAVINGS_PLAN_INVOICE",
    "ORDER_EXECUTED", "ssp_corporate_action_invoice_cash",
    "STOCK_PERK_REFUNDED", "benefits_spare_change_execution",
}

# Human-readable source labels
SOURCE_LABELS = {
    "trade_republic": "Trade Republic",
    "banque_populaire": "Banque Populaire",
    "bp": "Banque Populaire",
}


def _get_source_label(connector_id: str) -> str:
    """Get a readable label from the connector ID."""
    cid_lower = connector_id.lower()
    for key, label in SOURCE_LABELS.items():
        if key in cid_lower:
            return label
    return connector_id


@router.get("")
def get_cashflow(
    user: AuthUser = Depends(get_current_user),
    period: str = Query("1M", description="1W, 1M, 3M, 6M, 1Y, Max"),
    include_investments: bool = Query(True, description="Inclure les opérations d'investissement"),
):
    """Get cashflow for a period with transactions grouped by source."""
    if period == "Max":
        from_date = "2000-01-01"
    else:
        days = PERIOD_DAYS.get(period, 30)
        from_date = (date.today() - timedelta(days=days)).isoformat()

    to_date = date.today().isoformat()

    all_data = deps.manager.get_user_live_data(user.id)
    sources = []
    total_income = 0.0
    total_expenses = 0.0

    for cid, data in all_data.items():
        txs = data.get("transactions", [])
        if not txs:
            continue

        filtered_txs = []
        source_income = 0.0
        source_expenses = 0.0

        for tx in txs:
            if not isinstance(tx, dict):
                continue

            # Optionally skip investment operations
            raw_type = tx.get("raw_type", "")
            is_investment = raw_type in TR_INVESTMENT_TYPES
            if not include_investments and is_investment:
                continue

            tx_date = (tx.get("date", "") or "")[:10]
            if tx_date < from_date or tx_date > to_date:
                continue

            amount = float(tx.get("amount", 0))
            if amount == 0:
                continue

            label = tx.get("label", "")
            tx_type = "income" if amount > 0 else "expense"

            if amount > 0:
                source_income += amount
            else:
                source_expenses += amount

            filtered_txs.append({
                "date": tx_date,
                "label": label,
                "amount": amount,
                "type": tx_type,
            })

        if filtered_txs:
            filtered_txs.sort(key=lambda t: t["date"], reverse=True)
            sources.append({
                "source": cid,
                "label": _get_source_label(cid),
                "delta": source_income + source_expenses,
                "income": source_income,
                "expenses": source_expenses,
                "transactions": filtered_txs,
            })
            total_income += source_income
            total_expenses += source_expenses

    return {
        "period": period,
        "from": from_date,
        "to": to_date,
        "delta": total_income + total_expenses,
        "income": total_income,
        "expenses": total_expenses,
        "sources": sources,
    }
