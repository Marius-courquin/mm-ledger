from fastapi import APIRouter

from src.api import deps
from src.schemas.portfolio import PortfolioResponse, PositionResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _parse_position(p: dict, cat_type: str, connector_id: str) -> PositionResponse:
    qty = float(p.get("netSize", 0) or p.get("quantity", 0))
    avg = float(p.get("averageBuyIn", 0) or p.get("avg_price", 0))
    cur = float(p.get("currentPrice", 0) or p.get("current_price", 0))
    val = qty * cur if cur else 0
    invested = qty * avg
    pnl = val - invested if invested else 0
    return PositionResponse(
        connector_id=connector_id,
        account_id=p.get("accountId", connector_id),
        instrument=p.get("isin", "") or p.get("instrument", ""),
        name=p.get("name", ""),
        symbol=p.get("shortName", "") or p.get("symbol", ""),
        category=cat_type,
        quantity=qty,
        avg_price=avg,
        current_price=cur,
        value=val,
        pnl=pnl,
        pnl_pct=(pnl / invested * 100) if invested else 0,
        currency=p.get("currencyId", "EUR") or p.get("currency", "EUR"),
    )


@router.get("")
def get_portfolio(connector_id: str | None = None):
    """Returns portfolio grouped by account, each account grouped by category."""
    all_data = deps.manager.get_all_live_data()

    accounts = []
    grand_total_value = 0.0
    grand_total_invested = 0.0
    grand_total_cash = 0.0

    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue

        # Cash
        for b in data.get("balances", []):
            if isinstance(b, dict):
                grand_total_cash += float(b.get("amount", 0))

        # Positions — new format: list of account objects
        raw = data.get("positions", [])
        account_list = raw if isinstance(raw, list) else [raw] if isinstance(raw, dict) else []

        for acc_data in account_list:
            if not isinstance(acc_data, dict):
                continue

            acc_label = acc_data.get("label", acc_data.get("productType", "Unknown"))
            sec_acc_no = acc_data.get("secAccNo", "")
            product_type = acc_data.get("productType", "DEFAULT")

            categories_out = []
            acc_total_value = 0.0
            acc_total_invested = 0.0

            for cat in acc_data.get("categories", []):
                cat_type = cat.get("categoryType", "")
                positions = []
                for p in cat.get("positions", []):
                    pos = _parse_position(p, cat_type, cid)
                    positions.append(pos)
                    acc_total_value += pos.value
                    acc_total_invested += pos.quantity * pos.avg_price

                if positions:
                    cat_value = sum(p.value for p in positions)
                    cat_invested = sum(p.quantity * p.avg_price for p in positions)
                    cat_pnl = cat_value - cat_invested
                    categories_out.append({
                        "categoryType": cat_type,
                        "total_value": cat_value,
                        "total_invested": cat_invested,
                        "pnl": cat_pnl,
                        "pnl_pct": (cat_pnl / cat_invested * 100) if cat_invested else 0,
                        "positions": [p.model_dump() for p in positions],
                    })

            acc_pnl = acc_total_value - acc_total_invested
            # Find cash for this account
            acc_cash = 0.0
            for b in data.get("balances", []):
                if isinstance(b, dict):
                    # Match by productType or just use first cash entry
                    if b.get("productType") == product_type or not b.get("productType"):
                        acc_cash = float(b.get("amount", 0))

            # Split crypto and private equity into their own top-level sections
            SPLIT_CATEGORIES = {"cryptos": "Crypto", "privateMarkets": "Private Equity"}
            main_categories = []
            for cat_out in categories_out:
                cat_type = cat_out["categoryType"]
                if cat_type in SPLIT_CATEGORIES:
                    # Promote to its own account-level card
                    cat_value = cat_out["total_value"]
                    cat_invested = cat_out["total_invested"]
                    cat_pnl = cat_out["pnl"]
                    accounts.append({
                        "secAccNo": f"{sec_acc_no}_{cat_type}",
                        "label": SPLIT_CATEGORIES[cat_type],
                        "productType": cat_type.upper(),
                        "cash": 0,
                        "positions_value": cat_value,
                        "total_value": cat_value,
                        "total_invested": cat_invested,
                        "pnl": cat_pnl,
                        "pnl_pct": (cat_pnl / cat_invested * 100) if cat_invested else 0,
                        "categories": [cat_out],
                    })
                else:
                    main_categories.append(cat_out)

            # Main account with only stocksAndETFs etc.
            main_value = sum(c["total_value"] for c in main_categories)
            main_invested = sum(c["total_invested"] for c in main_categories)
            main_pnl = main_value - main_invested
            accounts.append({
                "secAccNo": sec_acc_no,
                "label": acc_label,
                "productType": product_type,
                "cash": acc_cash,
                "positions_value": main_value,
                "total_value": main_value + acc_cash,
                "total_invested": main_invested,
                "pnl": main_pnl,
                "pnl_pct": (main_pnl / main_invested * 100) if main_invested else 0,
                "categories": main_categories,
            })

            grand_total_value += acc_total_value
            grand_total_invested += acc_total_invested

    grand_total_value += grand_total_cash
    grand_total_pnl = (grand_total_value - grand_total_cash) - grand_total_invested

    # Order: main accounts first (CTO, PEA), then crypto, then private equity
    ORDER = {"DEFAULT": 0, "TAX_WRAPPER": 1, "PEA": 1, "CRYPTOS": 2, "PRIVATEMARKETS": 3}
    accounts.sort(key=lambda a: ORDER.get(a["productType"], 99))

    return {
        "total_value": grand_total_value,
        "total_cash": grand_total_cash,
        "total_invested": grand_total_invested,
        "total_pnl": grand_total_pnl,
        "total_pnl_pct": (grand_total_pnl / grand_total_invested * 100) if grand_total_invested else 0,
        "currency": "EUR",
        "accounts": accounts,
    }


@router.get("/{connector_id}")
def get_portfolio_by_connector(connector_id: str):
    return get_portfolio(connector_id=connector_id)
