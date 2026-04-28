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


# ── Task 4 : _current_value_bucket ──────────────────────────────────────────

def _seed_account_value(tmp_path, account_id="tr_CTO", total=5000.0):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(balance_snapshots).values(
            account_id=account_id, date="2026-04-27",
            cash=0, positions_value=total, total_value=total, positions=[],
        ))
    return engine


def test_current_value_bucket_amount_slice(tmp_path):
    engine = _seed_account_value(tmp_path, "livret_A", total=10000)
    target = {"type": "bucket"}
    slices = [{"account_id": "livret_A", "allocation_kind": "amount", "allocation_value": 1500}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 1500.0


def test_current_value_bucket_percent_slice(tmp_path):
    engine = _seed_account_value(tmp_path, "tr_CTO", total=10000)
    target = {"type": "bucket"}
    slices = [{"account_id": "tr_CTO", "allocation_kind": "percent", "allocation_value": 30}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 3000.0


def test_current_value_bucket_mixed_multi_account(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="tr_1", type="trade_republic"))
        conn.execute(insert(connectors).values(id="bp_1", type="woob_bank"))
        conn.execute(insert(accounts).values(id="cto", connector_id="tr_1", name="CTO", type="cto"))
        conn.execute(insert(accounts).values(id="livret", connector_id="bp_1", name="Livret", type="cash"))
        conn.execute(insert(balance_snapshots).values(
            account_id="cto", date="2026-04-27",
            cash=0, positions_value=10000, total_value=10000, positions=[],
        ))
        conn.execute(insert(balance_snapshots).values(
            account_id="livret", date="2026-04-27",
            cash=8000, positions_value=0, total_value=8000, positions=[],
        ))
    target = {"type": "bucket"}
    slices = [
        {"account_id": "cto", "allocation_kind": "percent", "allocation_value": 30},
        {"account_id": "livret", "allocation_kind": "amount", "allocation_value": 2500},
    ]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 5500.0


def test_current_value_bucket_amount_capped(tmp_path):
    engine = _seed_account_value(tmp_path, "livret", total=1000)
    target = {"type": "bucket"}
    slices = [{"account_id": "livret", "allocation_kind": "amount", "allocation_value": 5000}]
    val = compute_current_value(target, slices, engine, today=date(2026, 4, 28))
    assert val == 1000.0


# ── Task 5 : compute_rate ────────────────────────────────────────────────────

def _seed_history(tmp_path, account_id, dates_values):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id=account_id, connector_id="c", name="A", type="cto"))
        for d, v in dates_values:
            conn.execute(insert(balance_snapshots).values(
                account_id=account_id, date=d,
                cash=0, positions_value=v, total_value=v, positions=[],
            ))
    return engine


def test_rate_override(tmp_path):
    from src.services.target_progression import compute_rate
    engine = _seed_history(tmp_path, "a", [("2026-01-15", 1000), ("2026-04-15", 1300)])
    target = {"type": "bucket", "rate_override": 250.0}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert rate == 250.0
    assert source == "override"


def test_rate_auto_3_months(tmp_path):
    from src.services.target_progression import compute_rate
    engine = _seed_history(tmp_path, "a", [
        ("2026-01-28", 1000),
        ("2026-04-28", 1300),
    ])
    target = {"type": "bucket", "rate_override": None}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert abs(rate - 100.0) < 1.0
    assert source == "auto"


def test_rate_auto_no_history(tmp_path):
    from src.services.target_progression import compute_rate
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(connectors).values(id="c", type="trade_republic"))
        conn.execute(insert(accounts).values(id="a", connector_id="c", name="A", type="cto"))
    target = {"type": "bucket", "rate_override": None}
    slices = [{"account_id": "a", "allocation_kind": "percent", "allocation_value": 100}]
    rate, source = compute_rate(target, slices, engine, today=date(2026, 4, 28))
    assert rate == 0.0
    assert source == "auto"


# ── Task 6 : compute_eta ─────────────────────────────────────────────────────

def test_eta_reached():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=1200, rate=100)
    assert months is None
    assert status == "reached"


def test_eta_ok():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=100)
    assert months == 6.0
    assert status == "ok"


def test_eta_insufficient_zero():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=0)
    assert months is None
    assert status == "insufficient"


def test_eta_insufficient_negative():
    from src.services.target_progression import compute_eta
    months, status = compute_eta(target_amount=1000, current_value=400, rate=-50)
    assert months is None
    assert status == "insufficient"
