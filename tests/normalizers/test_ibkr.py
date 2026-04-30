import pytest
from decimal import Decimal
from src.normalizers.ibkr import IBKRNormalizer


def test_normalize_account():
    norm = IBKRNormalizer()
    raw = [{"account_id": "U24281721", "currency": "EUR"}]
    accs = norm.normalize_accounts(raw, connector_id="user1:ibkr-1")
    assert accs[0].id == "ibkr:U24281721"
    assert accs[0].kind == "securities"
    assert accs[0].tax_wrapper == "cto"


def test_normalize_position_asset_class_from_sec_type():
    norm = IBKRNormalizer()
    accs = norm.normalize_accounts(
        [{"account_id": "U1", "currency": "EUR"}], connector_id="user1:ibkr-1"
    )
    raw_pos = [{
        "account_id": "U1", "symbol": "AAPL", "secType": "STK",
        "isin": "US0378331005", "name": "Apple",
        "quantity": "10", "avg_price": "150", "current_price": "180",
    }]
    poss = norm.normalize_positions(raw_pos, accs)
    assert poss[0].asset_class == "equity"
    assert poss[0].value == Decimal("1800")
