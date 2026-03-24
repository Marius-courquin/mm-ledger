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


def test_wal_mode_enabled():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "test.db"
        engine = create_engine_and_tables(db_path)
        with engine.connect() as conn:
            result = conn.exec_driver_sql("PRAGMA journal_mode")
            mode = result.scalar()
            assert mode == "wal"
        engine.dispose()
