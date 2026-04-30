"""Normalizer Woob (banques FR).

Mappings :
- Account.type → kind (LOAN → liability)
- Account.label patterns → tax_wrapper (Livret A, LDD, etc.)
- ID préfixé `woob:{backend}:{account_id}`
"""
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from src.normalizers import register
from src.normalizers.base import Normalizer
from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition

# Constantes Woob (équivalentes à `from woob.capabilities.bank import Account`).
# Redéfinies ici pour ne pas faire dépendre le normalizer de woob (testabilité).
WOOB_TYPE_CHECKING = 1
WOOB_TYPE_SAVINGS = 2
WOOB_TYPE_LOAN = 3
WOOB_TYPE_MARKET = 4
WOOB_TYPE_DEPOSIT = 5
WOOB_TYPE_CARD = 6
WOOB_TYPE_LIFE_INSURANCE = 7
WOOB_TYPE_PEA = 8
WOOB_TYPE_PERP = 13

TYPE_TO_KIND = {
    WOOB_TYPE_CHECKING: "cash",
    WOOB_TYPE_SAVINGS: "cash",
    WOOB_TYPE_DEPOSIT: "cash",
    WOOB_TYPE_LOAN: "liability",
    WOOB_TYPE_CARD: "liability",
    WOOB_TYPE_MARKET: "securities",
    WOOB_TYPE_PEA: "securities",
    WOOB_TYPE_LIFE_INSURANCE: "securities",
    WOOB_TYPE_PERP: "securities",
}

TYPE_TO_TAX_WRAPPER = {
    WOOB_TYPE_PEA: "pea",
    WOOB_TYPE_LIFE_INSURANCE: "av",
    WOOB_TYPE_PERP: "per",
}

LABEL_PATTERNS = [
    (re.compile(r"\bLivret\s+A\b", re.IGNORECASE), "livret_a"),
    (re.compile(r"\bLivret\s+Jeune\b", re.IGNORECASE), "livret_jeune"),
    (re.compile(r"\bLDDS?\b", re.IGNORECASE), "ldds"),
    (re.compile(r"\bLEP\b", re.IGNORECASE), "lep"),
    (re.compile(r"\bCEL\b", re.IGNORECASE), "cel"),
    (re.compile(r"\bPEL\b", re.IGNORECASE), "pel"),
]


def _wrapper_from_label(label: str) -> str:
    """Inférer le tax_wrapper à partir du label du compte (Livret A, etc.)."""
    for pattern, wrapper in LABEL_PATTERNS:
        if pattern.search(label):
            return wrapper
    return "none"


class WoobNormalizer(Normalizer):
    def normalize_accounts(
        self, raw: list[dict], connector_id: str
    ) -> list[CanonicalAccount]:
        out: list[CanonicalAccount] = []
        for entry in raw:
            backend = entry.get("backend", "x")
            acc_id = f"woob:{backend}:{entry.get('id', '')}"
            woob_type = int(entry.get("type", WOOB_TYPE_CHECKING))
            kind = TYPE_TO_KIND.get(woob_type, "cash")
            tax = TYPE_TO_TAX_WRAPPER.get(woob_type)
            if not tax:
                # Inférer tax_wrapper à partir du label pour kind=cash
                tax = _wrapper_from_label(entry.get("label", "")) if kind == "cash" else "none"
            out.append(CanonicalAccount(
                id=acc_id,
                connector_id=connector_id,
                connector_type="woob_bank",
                label=entry.get("label", ""),
                kind=kind,
                tax_wrapper=tax,
                currency=entry.get("currency", "EUR"),
            ))
        return out

    def normalize_balances(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalBalance]:
        as_of = datetime.now(timezone.utc)
        by_lookup = {a.id: a for a in accounts}
        out: list[CanonicalBalance] = []
        for entry in raw:
            backend = entry.get("backend", "x")
            acc_id = f"woob:{backend}:{entry.get('id', '')}"
            account = by_lookup.get(acc_id)
            if not account:
                continue
            balance = Decimal(str(entry.get("balance", "0")))
            # Convention : kind=liability → total_value négatif.
            if account.kind == "liability":
                total = -abs(balance)
            else:
                total = balance
            out.append(CanonicalBalance(
                account_id=acc_id,
                cash=balance if account.kind != "securities" else None,
                positions_value=None,
                total_value=total,
                currency=entry.get("currency", "EUR"),
                as_of=as_of,
            ))
        return out

    def normalize_positions(
        self, raw: list[dict], accounts: list[CanonicalAccount]
    ) -> list[CanonicalPosition]:
        return []  # Woob ne remonte pas de positions par défaut


register("woob_bank", WoobNormalizer())
