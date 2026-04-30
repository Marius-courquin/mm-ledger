"""Normalizer IBKR."""
from datetime import datetime, timezone
from decimal import Decimal

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

SEC_TYPE_TO_ASSET_CLASS = {
    "STK": "equity", "ETF": "etf", "BOND": "bond",
    "CRYPTO": "crypto", "FUT": "other", "OPT": "other", "FOP": "other",
}


class IBKRNormalizer(Normalizer):
    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            acc_id = entry.get("account_id") or entry.get("accountId", "")
            out.append(CanonicalAccount(
                id=f"ibkr:{acc_id}",
                connector_id=connector_id,
                connector_type="ibkr",
                label=acc_id,
                kind="securities",
                tax_wrapper="cto",
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        out = []
        by_id = {a.id: a for a in accounts}
        for entry in raw:
            acc_id = f"ibkr:{entry.get('account_id') or entry.get('accountId', '')}"
            if acc_id not in by_id:
                continue
            cash = Decimal(str(entry.get("cash", "0")))
            pv = Decimal(str(entry.get("positions_value", "0")))
            out.append(CanonicalBalance(
                account_id=acc_id, cash=cash, positions_value=pv,
                total_value=cash + pv, currency=entry.get("currency", "EUR"),
                as_of=as_of,
            ))
        return out

    def normalize_positions(self, raw, accounts):
        out = []
        by_acc = {a.id: a for a in accounts}
        for pos in raw:
            acc_id = f"ibkr:{pos.get('account_id') or pos.get('accountId', '')}"
            if acc_id not in by_acc:
                continue
            sec_type = pos.get("secType", "STK").upper()
            asset_class = SEC_TYPE_TO_ASSET_CLASS.get(sec_type, "other")
            qty = Decimal(str(pos.get("quantity", 0)))
            avg = Decimal(str(pos.get("avg_price", 0)))
            cur_raw = pos.get("current_price")
            cur = Decimal(str(cur_raw)) if cur_raw else None
            value = qty * cur if cur else Decimal("0")
            out.append(CanonicalPosition(
                account_id=acc_id,
                symbol=pos.get("symbol", ""),
                isin=pos.get("isin"),
                name=pos.get("name", pos.get("symbol", "")),
                quantity=qty,
                average_price=avg if avg > 0 else None,
                current_price=cur,
                value=value,
                asset_class=asset_class,
                currency=pos.get("currency", "EUR"),
            ))
        return out


register("ibkr", IBKRNormalizer())
