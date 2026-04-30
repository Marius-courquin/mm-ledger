from datetime import datetime
from decimal import Decimal

from src.normalizers.types import CanonicalAccount, CanonicalBalance, CanonicalPosition


def test_canonical_account_minimal():
    acc = CanonicalAccount(
        id="tr:DA1234",
        connector_id="user1:tr-1",
        connector_type="trade_republic",
        label="PEA",
        kind="securities",
        tax_wrapper="pea",
    )
    assert acc.currency == "EUR"
    assert acc.tax_wrapper == "pea"


def test_canonical_balance_negative_for_liability():
    bal = CanonicalBalance(
        account_id="woob:bp:abc",
        total_value=Decimal("-3800.00"),
        as_of=datetime(2026, 4, 30, 10, 0, 0),
    )
    assert bal.total_value < 0


def test_canonical_position_value_decimal():
    pos = CanonicalPosition(
        account_id="tr:DA1234",
        symbol="AAPL",
        isin="US0378331005",
        name="Apple Inc.",
        quantity=Decimal("10"),
        current_price=Decimal("180.50"),
        value=Decimal("1805.00"),
        asset_class="equity",
    )
    assert pos.asset_class == "equity"
    assert pos.value == Decimal("1805.00")
