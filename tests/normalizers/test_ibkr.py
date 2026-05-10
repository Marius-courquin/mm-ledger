import pytest
from decimal import Decimal
from src.normalizers.ibkr import IBKRNormalizer


@pytest.fixture
def raw_accounts():
    return [{"id": "U24281721", "name": "U24281721", "type": "margin"}]


@pytest.fixture
def raw_positions():
    return [{
        "secAccNo": "U24281721", "productType": "DEFAULT",
        "label": "IBKR U24281721",
        "categories": [{
            "categoryType": "stocksAndETFs",
            "positions": [{
                "isin": "12345", "name": "Apple", "shortName": "AAPL",
                "netSize": 10.0, "averageBuyIn": 150.0, "currentPrice": 180.0,
                "currencyId": "EUR",
            }],
        }],
    }]


@pytest.fixture
def raw_balances():
    return [{
        "account_id": "U24281721", "accountNumber": "U24281721",
        "productType": "DEFAULT", "label": "IBKR U24281721",
        "amount": 1000.0, "cash": 1000.0,
        "total_value": 2800.0, "positions_value": 1800.0,
        "currency": "EUR",
    }]


def test_normalize_accounts_uses_id_field(raw_accounts):
    norm = IBKRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:ibkr-1")
    assert len(accs) == 1
    assert accs[0].id == "ibkr:U24281721"
    assert accs[0].label == "U24281721"
    assert accs[0].kind == "securities"
    assert accs[0].tax_wrapper == "cto"


def test_normalize_positions_parses_tr_shape(raw_accounts, raw_positions):
    norm = IBKRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:ibkr-1")
    poss = norm.normalize_positions(raw_positions, accs)
    assert len(poss) == 1
    p = poss[0]
    assert p.account_id == "ibkr:U24281721"
    assert p.symbol == "AAPL"
    assert p.asset_class == "equity"
    assert p.quantity == Decimal("10")
    assert p.value == Decimal("1800")


def test_normalize_balances(raw_accounts, raw_balances):
    norm = IBKRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:ibkr-1")
    bals = norm.normalize_balances(raw_balances, accs)
    assert len(bals) == 1
    b = bals[0]
    assert b.account_id == "ibkr:U24281721"
    assert b.cash == Decimal("1000")
    assert b.total_value == Decimal("2800")
