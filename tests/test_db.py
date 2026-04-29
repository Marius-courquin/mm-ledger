import tempfile
from pathlib import Path

from sqlalchemy import inspect

from src.db.engine import create_engine_and_tables
from src.db.models import connectors, accounts, balance_snapshots, transactions, performance


def test_tables_created():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine_and_tables(db_path)
        inspector = inspect(engine)
        table_names = inspector.get_table_names()
        assert "connectors" in table_names
        assert "accounts" in table_names
        assert "balance_snapshots" in table_names
        assert "transactions" in table_names
        assert "performance" in table_names
        engine.dispose()


def test_targets_tables_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import targets, target_slices
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "targets" in insp.get_table_names()
    assert "target_slices" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("targets")}
    assert {"id", "name", "type", "target_amount", "asset_account_id",
            "asset_symbol", "rate_override", "archived", "created_at"} <= cols
    cols = {c["name"] for c in insp.get_columns("target_slices")}
    assert {"id", "target_id", "account_id", "allocation_kind", "allocation_value"} <= cols


def test_loans_table_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import loans
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "loans" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("loans")}
    assert {"id", "name", "loan_type", "initial_capital", "monthly_payment",
            "total_months", "start_date", "archived", "created_at"} <= cols


def test_projection_tables_created(tmp_path):
    from src.db.engine import create_engine_and_tables
    from src.db.models import projection_settings, account_classification
    from sqlalchemy import inspect

    engine = create_engine_and_tables(tmp_path / "ledger.db")
    insp = inspect(engine)
    assert "projection_settings" in insp.get_table_names()
    assert "account_classification" in insp.get_table_names()
    cols = {c["name"] for c in insp.get_columns("projection_settings")}
    assert {"id", "cash_annual_rate", "market_annual_rate",
            "cash_monthly_contribution", "market_monthly_contribution",
            "horizon_years"} <= cols
    cols = {c["name"] for c in insp.get_columns("account_classification")}
    assert {"account_id", "category"} <= cols


def test_wal_mode_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine_and_tables(db_path)
        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA journal_mode")
            mode = result.scalar()
            assert mode == "wal"
        engine.dispose()
