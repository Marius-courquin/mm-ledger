"""Normalizer IBKR.

Le worker IBKR émet des données dans un shape TR-compatible (positions
nichées sous `categories[]`). On parse en conséquence.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

# IBKR n'expose pas de `secType` dans le shape TR-compatible — toutes les positions
# remontent sous categoryType="stocksAndETFs". On classifie par défaut "equity",
# en attendant un enrichissement futur.
CATEGORY_TO_ASSET_CLASS = {
    "stocksAndETFs": "equity",
    "stocks": "equity",
    "etfs": "etf",
    "bonds": "bond",
    "cryptos": "crypto",
    "privateMarkets": "private",
    "derivatives": "other",
}


def _decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


class IBKRNormalizer(Normalizer):
    def __init__(self) -> None:
        self._positions_by_account: dict[str, list[CanonicalPosition]] = {}

    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            acc_id = entry.get("id") or entry.get("account_id") or entry.get("accountId", "")
            if not acc_id:
                continue
            out.append(CanonicalAccount(
                id=f"ibkr:{acc_id}",
                connector_id=connector_id,
                connector_type="ibkr",
                label=entry.get("name") or acc_id,
                kind="securities",
                tax_wrapper="cto",
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_positions(self, raw, accounts):
        positions: list[CanonicalPosition] = []
        self._positions_by_account = {}
        for acc_data in raw:
            sec_no = acc_data.get("secAccNo", "")
            account_id = f"ibkr:{sec_no}"
            for cat in acc_data.get("categories", []):
                cat_type = cat.get("categoryType", "")
                asset_class = CATEGORY_TO_ASSET_CLASS.get(cat_type, "other")
                for pos in cat.get("positions", []):
                    qty = _decimal(pos.get("netSize") or pos.get("quantity")) or Decimal("0")
                    avg = _decimal(pos.get("averageBuyIn") or pos.get("avg_price"))
                    cur = _decimal(pos.get("currentPrice") or pos.get("current_price"))
                    value = qty * cur if cur else Decimal("0")
                    canonical = CanonicalPosition(
                        account_id=account_id,
                        symbol=pos.get("shortName") or pos.get("symbol") or pos.get("isin", ""),
                        isin=pos.get("isin"),
                        name=pos.get("name", ""),
                        quantity=qty,
                        average_price=avg if avg and avg > 0 else None,
                        current_price=cur,
                        value=value,
                        asset_class=asset_class,
                        currency=pos.get("currencyId", "EUR"),
                    )
                    positions.append(canonical)
                    self._positions_by_account.setdefault(account_id, []).append(canonical)
        return positions

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        out = []
        by_id = {a.id: a for a in accounts}
        for entry in raw:
            raw_id = entry.get("account_id") or entry.get("accountNumber") or entry.get("accountId", "")
            acc_id = f"ibkr:{raw_id}"
            if acc_id not in by_id:
                continue
            cash = _decimal(entry.get("cash", 0)) or Decimal("0")
            pv_raw = entry.get("positions_value")
            pv = _decimal(pv_raw) if pv_raw is not None else None
            total_raw = entry.get("total_value")
            total = _decimal(total_raw) if total_raw is not None else (cash + (pv or Decimal("0")))
            out.append(CanonicalBalance(
                account_id=acc_id, cash=cash, positions_value=pv,
                total_value=total, currency=entry.get("currency", "EUR"),
                as_of=as_of,
            ))
        return out


register("ibkr", IBKRNormalizer())
