"""Normalizer Trade Republic.

Mappings :
- productType → (label, kind, tax_wrapper)
- categoryType → asset_class
- ID préfixé `tr:{securitiesAccountNumber}`
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

PRODUCT_TYPE_MAP = {
    # productType : (label, kind, tax_wrapper)
    "DEFAULT":        ("CTO", "securities", "cto"),
    "TAX_WRAPPER":    ("PEA", "securities", "pea"),
    "PEA":            ("PEA", "securities", "pea"),
    "CRYPTO":         ("Crypto", "securities", "none"),
    "PRIVATE_EQUITY": ("Private Equity", "securities", "none"),
}

CATEGORY_TO_ASSET_CLASS = {
    "stocks": "equity",
    "etfs": "etf",
    "bonds": "bond",
    "cryptos": "crypto",
    "privateMarkets": "private",
    "derivatives": "other",
}


def _decimal(value: Any) -> Decimal:
    if value is None or value == "":
        return Decimal("0")
    return Decimal(str(value))


class TRNormalizer(Normalizer):
    def __init__(self) -> None:
        self._positions_by_account: dict[str, list[CanonicalPosition]] = {}

    def normalize_accounts(
        self, raw: list[dict], connector_id: str
    ) -> list[CanonicalAccount]:
        out: list[CanonicalAccount] = []
        for entry in raw:
            sec_no = entry.get("securitiesAccountNumber") or entry.get("cashAccountNumber")
            if not sec_no:
                continue
            product_type = entry.get("productType", "DEFAULT")
            label, kind, tax = PRODUCT_TYPE_MAP.get(
                product_type, (product_type, "securities", "none")
            )
            out.append(CanonicalAccount(
                id=f"tr:{sec_no}",
                connector_id=connector_id,
                connector_type="trade_republic",
                label=label,
                kind=kind,
                tax_wrapper=tax,
                currency=entry.get("currencyId", "EUR"),
            ))
        return out

    def normalize_positions(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalPosition]:
        positions: list[CanonicalPosition] = []
        self._positions_by_account = {}
        for acc_data in raw:
            sec_no = acc_data.get("secAccNo", "")
            account_id = f"tr:{sec_no}"
            for cat in acc_data.get("categories", []):
                cat_type = cat.get("categoryType", "")
                asset_class = CATEGORY_TO_ASSET_CLASS.get(cat_type, "other")
                for pos in cat.get("positions", []):
                    qty = _decimal(pos.get("netSize") or pos.get("quantity"))
                    avg = _decimal(pos.get("averageBuyIn") or pos.get("avg_price"))
                    cur_raw = pos.get("currentPrice") or pos.get("current_price")
                    cur = _decimal(cur_raw) if cur_raw else None
                    value = qty * cur if cur else Decimal("0")
                    canonical = CanonicalPosition(
                        account_id=account_id,
                        symbol=pos.get("shortName") or pos.get("symbol") or pos.get("isin", ""),
                        isin=pos.get("isin"),
                        name=pos.get("name", ""),
                        quantity=qty,
                        average_price=avg if avg > 0 else None,
                        current_price=cur,
                        value=value,
                        asset_class=asset_class,
                        currency=pos.get("currencyId", "EUR"),
                    )
                    positions.append(canonical)
                    self._positions_by_account.setdefault(account_id, []).append(canonical)
        return positions

    def normalize_balances(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalBalance]:
        as_of = datetime.now(timezone.utc)
        out: list[CanonicalBalance] = []
        for cash_entry in raw:
            cash_account_no = cash_entry.get("accountNumber", "")
            target_account = None
            sec_candidate = cash_entry.get("secAccNo")
            if sec_candidate:
                target_account = next(
                    (a for a in accounts if a.id == f"tr:{sec_candidate}"), None
                )
            if target_account is None and cash_account_no:
                # Heuristic : CA1111 ↔ DA1111 (suffix-based pairing)
                suffix = cash_account_no[2:] if len(cash_account_no) > 2 else cash_account_no
                target_account = next(
                    (a for a in accounts if a.id.endswith(suffix)), None
                )
            if target_account is None:
                continue

            cash = _decimal(cash_entry.get("amount", 0))
            pos_list = self._positions_by_account.get(target_account.id, [])
            positions_value = (
                sum((p.value for p in pos_list), start=Decimal("0"))
                if pos_list else None
            )
            total = cash + (positions_value or Decimal("0"))
            out.append(CanonicalBalance(
                account_id=target_account.id,
                cash=cash,
                positions_value=positions_value,
                total_value=total,
                currency=cash_entry.get("currencyId", "EUR"),
                as_of=as_of,
            ))
        return out


register("trade_republic", TRNormalizer())
