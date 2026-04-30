"""Tests Woob normalizer.

Fixtures = payloads bruts tels qu'émis par le worker Woob (cf.
src/connectors/woob_bank.py fetch_accounts / fetch_balances).
"""
from decimal import Decimal

import pytest

from src.normalizers.woob_bank import WoobNormalizer


@pytest.fixture
def raw_accounts():
    """Format émis par le worker Woob (cf. src/connectors/woob_bank.py)."""
    return [
        {
            "id": "abc123", "backend": "bp", "label": "Compte individuel M CHARLES",
            "type": 1, "balance": "971.76", "currency": "EUR",  # TYPE_CHECKING=1
        },
        {
            "id": "abc456", "backend": "bp", "label": "Livret A-Particuliers M CHARLES",
            "type": 2, "balance": "12345.30", "currency": "EUR",  # TYPE_SAVINGS=2
        },
        {
            "id": "abc789", "backend": "bp", "label": "Livret Jeune M CHARLES",
            "type": 2, "balance": "100.00", "currency": "EUR",
        },
        {
            "id": "abc999", "backend": "bp", "label": "Vcc - Pret Jeune Standard M CHARLES",
            "type": 3, "balance": "-4000.00", "currency": "EUR",  # TYPE_LOAN=3
        },
    ]


def test_normalize_loan_kind_liability(raw_accounts):
    """TYPE_LOAN → kind=liability."""
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    by_id = {a.id: a for a in accs}
    loan = by_id["woob:bp:abc999"]
    assert loan.kind == "liability"
    assert loan.label == "Vcc - Pret Jeune Standard M CHARLES"
    assert loan.tax_wrapper == "none"


def test_normalize_livret_a_tax_wrapper(raw_accounts):
    """Label patterns → tax_wrapper (Livret A, Livret Jeune)."""
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    by_id = {a.id: a for a in accs}
    assert by_id["woob:bp:abc456"].tax_wrapper == "livret_a"
    assert by_id["woob:bp:abc789"].tax_wrapper == "livret_jeune"


def test_normalize_balances_loan_negative(raw_accounts):
    """kind=liability → total_value négatif."""
    norm = WoobNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:woob-1")
    bals = norm.normalize_balances(raw_accounts, accs)
    by_id = {b.account_id: b for b in bals}
    assert by_id["woob:bp:abc999"].total_value == Decimal("-4000.00")
    assert by_id["woob:bp:abc456"].total_value == Decimal("12345.30")
