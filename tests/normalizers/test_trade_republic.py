"""Tests du TR normalizer.

Fixtures = payloads bruts tels qu'émis par le worker TR (cf.
src/connectors/trade_republic.py auto_fetch).
"""
from decimal import Decimal

import pytest

from src.normalizers.trade_republic import TRNormalizer


@pytest.fixture
def raw_accounts():
    """Payload tel que retourné par accountPairs (extrait `accounts`)."""
    return [
        {"securitiesAccountNumber": "DA1111", "cashAccountNumber": "CA1111", "productType": "DEFAULT"},
        {"securitiesAccountNumber": "DA2222", "cashAccountNumber": "CA2222", "productType": "TAX_WRAPPER"},
        {"securitiesAccountNumber": "DA3333", "cashAccountNumber": "CA3333", "productType": "CRYPTO"},
    ]


@pytest.fixture
def raw_cash():
    return [
        {"accountNumber": "CA1111", "amount": "150.50", "currencyId": "EUR"},
        {"accountNumber": "CA2222", "amount": "0.00", "currencyId": "EUR"},
        {"accountNumber": "CA3333", "amount": "10.00", "currencyId": "EUR"},
    ]


@pytest.fixture
def raw_positions():
    """Liste d'objets account_data tels qu'émis par auto_fetch (event positions)."""
    return [
        {
            "secAccNo": "DA1111", "productType": "DEFAULT", "label": "CTO",
            "categories": [
                {
                    "categoryType": "stocks",
                    "positions": [
                        {
                            "isin": "US0378331005", "shortName": "AAPL", "name": "Apple Inc.",
                            "netSize": "5", "averageBuyIn": "150", "currentPrice": 180.0,
                            "accountId": "DA1111",
                        }
                    ],
                }
            ],
        },
        {
            "secAccNo": "DA2222", "productType": "TAX_WRAPPER", "label": "PEA",
            "categories": [
                {
                    "categoryType": "etfs",
                    "positions": [
                        {
                            "isin": "FR0010315770", "shortName": "CW8", "name": "Amundi MSCI World",
                            "netSize": "20", "averageBuyIn": "350", "currentPrice": 400.0,
                            "accountId": "DA2222",
                        }
                    ],
                }
            ],
        },
        {
            "secAccNo": "DA3333", "productType": "CRYPTO", "label": "Crypto",
            "categories": [
                {
                    "categoryType": "cryptos",
                    "positions": [
                        {
                            "isin": "BTC", "shortName": "BTC", "name": "Bitcoin",
                            "netSize": "0.01", "averageBuyIn": "30000", "currentPrice": 60000.0,
                            "accountId": "DA3333",
                        }
                    ],
                }
            ],
        },
    ]


def test_normalize_accounts_maps_product_type(raw_accounts):
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    by_id = {a.id: a for a in accs}
    assert by_id["tr:DA1111"].label == "CTO"
    assert by_id["tr:DA1111"].kind == "securities"
    assert by_id["tr:DA1111"].tax_wrapper == "cto"
    assert by_id["tr:DA2222"].label == "PEA"
    assert by_id["tr:DA2222"].tax_wrapper == "pea"
    assert by_id["tr:DA3333"].label == "Crypto"


def test_normalize_balances_pea_no_longer_zero(raw_accounts, raw_cash, raw_positions):
    """Régression : avant fix, le PEA renvoyait 0€ à cause du mismatch sec/cash."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    norm.normalize_positions(raw_positions, accs)
    bals = norm.normalize_balances(raw_cash, accs)
    by_id = {b.account_id: b for b in bals}
    # PEA = 0 cash + 20 * 400 = 8000 (positions_value)
    assert by_id["tr:DA2222"].total_value == Decimal("8000.00")
    assert by_id["tr:DA2222"].positions_value == Decimal("8000.00")
    # CTO = 150.50 + 5 * 180 = 1050.50
    assert by_id["tr:DA1111"].total_value == Decimal("1050.50")


def test_normalize_positions_includes_crypto(raw_positions, raw_accounts):
    """Régression : crypto + private equity étaient absents de la valo."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(raw_accounts, connector_id="user1:tr-1")
    poss = norm.normalize_positions(raw_positions, accs)
    by_account = {p.account_id: p for p in poss}
    assert "tr:DA3333" in by_account
    assert by_account["tr:DA3333"].asset_class == "crypto"
    assert by_account["tr:DA3333"].value == Decimal("600.00")  # 0.01 * 60000


def test_normalize_positions_handles_private_markets_without_price():
    """Private equity n'a pas de currentPrice — value = 0, current_price = None."""
    norm = TRNormalizer()
    accs = norm.normalize_accounts(
        [{"securitiesAccountNumber": "DA4444", "cashAccountNumber": "CA4444", "productType": "PRIVATE_EQUITY"}],
        connector_id="user1:tr-1",
    )
    raw_pos = [{
        "secAccNo": "DA4444", "productType": "PRIVATE_EQUITY", "label": "Private Equity",
        "categories": [{
            "categoryType": "privateMarkets",
            "positions": [{
                "isin": "PE001", "shortName": "PE Fund", "name": "Private Fund X",
                "netSize": "1", "averageBuyIn": "10000", "accountId": "DA4444",
            }],
        }],
    }]
    poss = norm.normalize_positions(raw_pos, accs)
    assert len(poss) == 1
    assert poss[0].asset_class == "private"
    assert poss[0].current_price is None
    assert poss[0].value == Decimal("0")
