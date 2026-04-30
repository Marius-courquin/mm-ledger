"""Tests Enable Banking normalizer.

Fixtures = payloads bruts tels qu'émis par Enable Banking PSD2 API
(cf. src/api/banking.py).
"""
from decimal import Decimal

import pytest

from src.normalizers.enable_banking import BankingNormalizer


@pytest.fixture
def raw_accounts():
    """Format émis par Enable Banking (PSD2)."""
    return [
        {
            "uid": "uid-1", "name": "Compte courant", "product": "CHECKING",
            "cashAccountType": "CACC", "currency": "EUR",
            "balances": [{"balanceAmount": {"amount": "500.00", "currency": "EUR"}}],
        },
        {
            "uid": "uid-2", "name": "Crédit auto", "product": "LOAN",
            "cashAccountType": "LOAN", "currency": "EUR",
            "balances": [{"balanceAmount": {"amount": "-15000.00", "currency": "EUR"}}],
        },
    ]


def test_normalize_loan(raw_accounts):
    """LOAN cashAccountType → kind=liability."""
    norm = BankingNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:eb-1")
    by_id = {a.id: a for a in accs}
    assert by_id["eb:uid-2"].kind == "liability"


def test_normalize_balances_negative(raw_accounts):
    """kind=liability → total_value négatif."""
    norm = BankingNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:eb-1")
    bals = norm.normalize_balances(raw_accounts, accs)
    by_id = {b.account_id: b for b in bals}
    assert by_id["eb:uid-2"].total_value == Decimal("-15000.00")
