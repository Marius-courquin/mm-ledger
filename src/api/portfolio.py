from fastapi import APIRouter, Depends

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.schemas.portfolio import PositionResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("")
def get_portfolio(
    connector_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """Portfolio agrégé par compte.

    Lit `positions` (CanonicalPosition list) + `balances` (CanonicalBalance list)
    + `accounts` (CanonicalAccount list) du manager.
    """
    all_data = deps.manager.get_user_live_data(user.id)

    accounts_out: list[dict] = []
    grand_total_value = 0.0
    grand_total_invested = 0.0
    grand_total_cash = 0.0

    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue

        accounts = data.get("accounts", [])
        balances = data.get("balances", [])
        positions = data.get("positions", [])

        balances_by_account = {b.account_id: b for b in balances}
        positions_by_account: dict[str, list] = {}
        for pos in positions:
            positions_by_account.setdefault(pos.account_id, []).append(pos)

        for acc in accounts:
            bal = balances_by_account.get(acc.id)
            cash = float(bal.cash) if bal and bal.cash is not None else 0.0
            grand_total_cash += cash

            acc_positions = positions_by_account.get(acc.id, [])
            acc_total_value = 0.0
            acc_total_invested = 0.0

            positions_out = []
            for pos in acc_positions:
                qty = float(pos.quantity)
                avg = float(pos.average_price) if pos.average_price else 0.0
                cur = float(pos.current_price) if pos.current_price else None
                val = float(pos.value) if pos.value else None
                invested = qty * avg
                pnl = (val - invested) if (val is not None and invested) else None
                pnl_pct = (pnl / invested * 100) if (pnl is not None and invested) else None

                if val is not None:
                    acc_total_value += val
                acc_total_invested += invested

                positions_out.append(PositionResponse(
                    connector_id=acc.connector_id,
                    account_id=acc.id,
                    instrument=pos.isin or "",
                    name=pos.name,
                    symbol=pos.symbol,
                    asset_class=pos.asset_class,
                    category=pos.asset_class,
                    quantity=qty,
                    avg_price=avg if avg else None,
                    current_price=cur,
                    value=val,
                    pnl=pnl,
                    pnl_pct=pnl_pct,
                    currency=pos.currency,
                ).model_dump())

            grand_total_value += acc_total_value
            grand_total_invested += acc_total_invested

            accounts_out.append({
                "account_id": acc.id,
                "label": acc.label,
                "kind": acc.kind,
                "tax_wrapper": acc.tax_wrapper,
                "cash": cash,
                "total_value": acc_total_value + cash,
                "total_invested": acc_total_invested,
                "positions": positions_out,
            })

    return {
        "accounts": accounts_out,
        "total_cash": grand_total_cash,
        "total_value": grand_total_value + grand_total_cash,
        "total_invested": grand_total_invested,
    }


@router.get("/{connector_id}")
def get_portfolio_by_connector(connector_id: str, user: AuthUser = Depends(get_current_user)):
    return get_portfolio(connector_id=connector_id, user=user)
