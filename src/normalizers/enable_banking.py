"""Normalizer Enable Banking (PSD2).

⚠️ TODO : Enable Banking ne passe pas (encore) par ConnectorManager — son API
(`src/api/banking.py`) appelle directement le client HTTP. Ce normalizer ne sera
invoqué que quand `banking` aura un ConnectorWorker dans le manager. Garder le
code aligné pour le jour où ce sera le cas.
"""
from datetime import datetime, timezone
from decimal import Decimal

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance

PSD2_TYPE_TO_KIND = {
    "CACC": "cash", "SVGS": "cash", "MOMA": "cash",
    "LOAN": "liability", "CARD": "liability",
}


class BankingNormalizer(Normalizer):
    def normalize_accounts(self, raw, connector_id):
        out = []
        for entry in raw:
            psd2_type = (entry.get("cashAccountType") or "CACC").upper()
            kind = PSD2_TYPE_TO_KIND.get(psd2_type, "cash")
            out.append(CanonicalAccount(
                id=f"eb:{entry.get('uid', '')}",
                connector_id=connector_id,
                connector_type="banking",
                label=entry.get("name") or entry.get("product", ""),
                kind=kind,
                tax_wrapper="none",
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(self, raw, accounts):
        as_of = datetime.now(timezone.utc)
        by_id = {a.id: a for a in accounts}
        out = []
        for entry in raw:
            acc_id = f"eb:{entry.get('uid', '')}"
            account = by_id.get(acc_id)
            if not account:
                continue
            balances = entry.get("balances", [])
            if not balances:
                continue
            amount_raw = balances[0].get("balanceAmount", {}).get("amount", "0")
            amount = Decimal(str(amount_raw))
            if account.kind == "liability":
                total = -abs(amount)
            else:
                total = amount
            out.append(CanonicalBalance(
                account_id=acc_id, cash=amount,
                positions_value=None, total_value=total,
                currency=entry.get("currency", "EUR"), as_of=as_of,
            ))
        return out

    def normalize_positions(self, raw, accounts):
        return []


register("banking", BankingNormalizer())
