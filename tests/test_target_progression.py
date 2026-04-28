from datetime import date
from sqlalchemy import insert
from src.db.engine import create_engine_and_tables
from src.db.models import accounts, balance_snapshots, connectors
from src.services.target_progression import compute_current_value


def _seed_position(tmp_path, symbol="IWDA", value=900.0):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(accounts).values(id="tr_CTO", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id="tr_CTO", date="2026-04-27",
            cash=100, positions_value=value, total_value=100 + value,
            positions=[{"symbol": symbol, "qty": 10, "price": value/10, "value": value}],
        ))
    return engine


def test_current_value_asset_existing(tmp_path):
    engine = _seed_position(tmp_path, symbol="IWDA", value=1234.5)
    target = {"type": "asset", "asset_account_id": "tr_CTO", "asset_symbol": "IWDA"}
    val = compute_current_value(target, [], engine, today=date(2026, 4, 28))
    assert val == 1234.5


def test_current_value_asset_missing(tmp_path):
    engine = _seed_position(tmp_path, symbol="IWDA", value=900)
    target = {"type": "asset", "asset_account_id": "tr_CTO", "asset_symbol": "VWCE"}
    val = compute_current_value(target, [], engine, today=date(2026, 4, 28))
    assert val == 0.0
