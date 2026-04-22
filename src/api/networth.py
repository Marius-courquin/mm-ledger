from datetime import date, timedelta
from fastapi import APIRouter, Query, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser

router = APIRouter(prefix="/api/net-worth", tags=["net-worth"])


@router.get("")
def get_net_worth(user: AuthUser = Depends(get_current_user)):
    """Compute live net worth from all connected workers."""
    all_data = deps.manager.get_user_live_data(user.id)

    bank_accounts = []
    investment_accounts = []
    bank_total = 0.0
    investments_total = 0.0
    investments_invested = 0.0

    for cid, data in all_data.items():
        has_positions = bool(data.get("positions"))
        seen_account_ids = set()

        # Balances event (TR cash format: [{accountNumber, amount}], BP format: [{account_id, amount}])
        for b in data.get("balances", []):
            if not isinstance(b, dict):
                continue
            amount = float(b.get("amount", 0) or b.get("total_value", 0))
            name = b.get("label") or b.get("name") or b.get("account_id") or cid
            acc_id = b.get("account_id") or b.get("accountNumber") or ""
            seen_account_ids.add(acc_id)

            if has_positions:
                investment_accounts.append({"name": f"Espèces {name}", "value": amount, "source": cid, "type": "investment"})
                investments_total += amount
            else:
                bank_accounts.append({"name": name, "value": amount, "source": cid, "type": "bank"})
                bank_total += amount

        # Also check accounts data for balances (BP sends balance in accounts event too)
        for acc in data.get("accounts", []):
            if not isinstance(acc, dict):
                continue
            acc_id = acc.get("id", "")
            if acc_id in seen_account_ids:
                continue  # Already counted from balances event
            balance = acc.get("balance")
            if balance is None:
                continue
            amount = float(balance)
            name = acc.get("name") or acc.get("label") or acc_id
            if has_positions:
                investment_accounts.append({"name": name, "value": amount, "source": cid, "type": "investment"})
                investments_total += amount
            else:
                bank_accounts.append({"name": name, "value": amount, "source": cid, "type": "bank"})
                bank_total += amount

        # Positions (TR, IBKR)
        raw_positions = data.get("positions", [])
        if isinstance(raw_positions, list):
            for acc_data in raw_positions:
                if not isinstance(acc_data, dict):
                    continue
                acc_label = acc_data.get("label", cid)
                acc_value = 0.0
                acc_invested = 0.0
                for cat in acc_data.get("categories", []):
                    for pos in cat.get("positions", []):
                        cur_raw = pos.get("currentPrice") or pos.get("current_price")
                        cur = float(cur_raw) if cur_raw else 0
                        qty = float(pos.get("netSize", 0) or pos.get("quantity", 0))
                        avg = float(pos.get("averageBuyIn", 0) or pos.get("avg_price", 0))
                        if cur > 0:
                            acc_value += qty * cur
                        acc_invested += qty * avg
                if acc_value > 0:
                    investment_accounts.append({"name": acc_label, "value": acc_value, "source": cid, "type": "investment"})
                    investments_total += acc_value
                    investments_invested += acc_invested

    total = bank_total + investments_total
    pnl = investments_total - investments_invested if investments_invested else 0
    pnl_pct = (pnl / investments_invested * 100) if investments_invested else 0

    return {
        "total": total,
        "currency": "EUR",
        "bank_total": bank_total,
        "investments_total": investments_total,
        "investments_pnl": pnl,
        "investments_pnl_pct": pnl_pct,
        "breakdown": bank_accounts + investment_accounts,
    }


@router.get("/history")
def get_net_worth_history(
    user: AuthUser = Depends(get_current_user),
    frm: str = Query(None, alias="from"),
    to: str = None,
):
    """Return daily net worth snapshots for the chart."""
    from sqlalchemy import select
    from src.db.models import net_worth_snapshots

    frm = frm or (date.today() - timedelta(days=30)).isoformat()
    to = to or date.today().isoformat()

    stmt = select(net_worth_snapshots).where(
        net_worth_snapshots.c.date >= frm,
        net_worth_snapshots.c.date <= to,
    ).order_by(net_worth_snapshots.c.date)

    with deps.get_ledger(user.id).connect() as conn:
        rows = conn.execute(stmt).fetchall()

    return [
        {"date": r.date, "total": r.total, "bank_total": r.bank_total, "investments_total": r.investments_total}
        for r in rows
    ]
