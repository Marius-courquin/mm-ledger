from fastapi import APIRouter

from src.api import deps
from src.schemas.portfolio import PortfolioResponse, PositionResponse

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _build_portfolio(connector_id: str | None = None) -> PortfolioResponse:
    all_data = deps.manager.get_all_live_data()
    positions = []
    total_cash = 0.0

    for cid, data in all_data.items():
        if connector_id and cid != connector_id:
            continue

        # Parse balances (availableCash returns a list like [{"currencyId":"EUR","amount":1234.56}])
        for b in data.get("balances", []):
            if isinstance(b, dict):
                total_cash += float(b.get("amount", 0))

        # Parse positions (compactPortfolioByType returns {categories: [{categoryType, positions: [...]}]})
        raw_positions = data.get("positions", [])
        if isinstance(raw_positions, dict):
            # TR format: {categories: [{categoryType, positions: [{netSize, averageBuyIn, ...}]}]}
            for cat in raw_positions.get("categories", []):
                cat_type = cat.get("categoryType", "")
                for p in cat.get("positions", []):
                    qty = float(p.get("netSize", 0))
                    avg = float(p.get("averageBuyIn", 0))
                    cur = float(p.get("currentPrice", 0))
                    val = qty * cur if cur else float(p.get("currentValue", 0))
                    invested = qty * avg
                    pnl = val - invested if invested else 0
                    positions.append(PositionResponse(
                        connector_id=cid,
                        account_id=p.get("accountId", cid),
                        instrument=p.get("isin", ""),
                        name=p.get("name", ""),
                        symbol=p.get("shortName", ""),
                        category=cat_type,
                        quantity=qty,
                        avg_price=avg,
                        current_price=cur,
                        value=val,
                        pnl=pnl,
                        pnl_pct=(pnl / invested * 100) if invested else 0,
                        currency=p.get("currencyId", "EUR"),
                    ))
        elif isinstance(raw_positions, list):
            for p in raw_positions:
                if isinstance(p, dict):
                    positions.append(PositionResponse(
                        connector_id=cid,
                        account_id=p.get("account_id", cid),
                        instrument=p.get("instrument", ""),
                        name=p.get("name", ""),
                        symbol=p.get("symbol", ""),
                        category=p.get("category", ""),
                        quantity=float(p.get("quantity", 0)),
                        avg_price=float(p.get("avg_price", 0)),
                        current_price=float(p.get("current_price", 0)),
                        value=float(p.get("value", 0)),
                        pnl=float(p.get("pnl", 0)),
                        pnl_pct=float(p.get("pnl_pct", 0)),
                        currency=p.get("currency", "EUR"),
                    ))

    total_positions_value = sum(p.value for p in positions)
    total_invested = sum(p.quantity * p.avg_price for p in positions)
    total_value = total_positions_value + total_cash
    total_pnl = total_positions_value - total_invested if total_invested else 0

    return PortfolioResponse(
        total_value=total_value,
        total_invested=total_invested,
        total_pnl=total_pnl,
        total_pnl_pct=(total_pnl / total_invested * 100) if total_invested else 0,
        currency="EUR",
        positions=positions,
    )


@router.get("", response_model=PortfolioResponse)
def get_portfolio(connector_id: str | None = None):
    return _build_portfolio(connector_id)


@router.get("/{connector_id}", response_model=PortfolioResponse)
def get_portfolio_by_connector(connector_id: str):
    return _build_portfolio(connector_id)
