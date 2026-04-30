import time

from src.connectors.base import ConnectorWorker
from src.manager import ConnectorManager


class FakeWorker(ConnectorWorker):
    def connect(self, credentials: dict):
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self):
        pass

    def fetch_accounts(self) -> list[dict]:
        return [{"id": "acc_1", "name": "Test"}]

    def fetch_positions(self) -> list[dict]:
        return []

    def fetch_balances(self) -> list[dict]:
        return [{"account_id": "acc_1", "cash": 100.0}]

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str):
        pass


class FailingWorker(ConnectorWorker):
    def connect(self, credentials: dict):
        self.event_queue.put({"type": "error", "message": "boom"})

    def disconnect(self):
        pass

    def fetch_accounts(self) -> list[dict]:
        return []

    def fetch_positions(self) -> list[dict]:
        return []

    def fetch_balances(self) -> list[dict]:
        return []

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str):
        pass


class KeyCapturingWorker(ConnectorWorker):
    def connect(self, credentials: dict):
        key = self.config.get("worker_key", "MISSING")
        self.event_queue.put({"type": "status", "state": "connected", "detail": key})

    def disconnect(self):
        pass

    def fetch_accounts(self) -> list[dict]:
        return []

    def fetch_positions(self) -> list[dict]:
        return []

    def fetch_balances(self) -> list[dict]:
        return []

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str):
        pass


def test_spawn_and_stop():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {"token": "abc"})
    time.sleep(0.5)
    status = mgr.get_status("test_1")
    assert status["state"] == "connected"
    mgr.stop("test_1")
    time.sleep(0.3)
    status = mgr.get_status("test_1")
    assert status["state"] == "disconnected"


def test_send_command_and_collect():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {"token": "abc"})
    time.sleep(0.5)
    mgr.send_command("test_1", {"type": "fetch_accounts"})
    time.sleep(0.5)
    events = mgr.collect_events()
    account_events = [e for e in events if e.get("type") == "accounts"]
    assert len(account_events) >= 1
    assert account_events[0]["data"][0]["id"] == "acc_1"
    mgr.stop("test_1")


def test_health_check():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("test_1", "fake", {})
    time.sleep(0.5)
    health = mgr.health_check()
    assert "test_1" in health
    assert health["test_1"] == "connected"
    mgr.stop_all()


def test_error_event_transitions_state_to_error():
    mgr = ConnectorManager()
    mgr.register_worker_class("failing", FailingWorker)
    mgr.spawn("err_1", "failing", {})
    time.sleep(0.5)
    status = mgr.get_status("err_1")
    assert status["state"] == "error"
    assert status["detail"] == "boom"
    mgr.stop("err_1")


def test_worker_receives_worker_key_in_config():
    mgr = ConnectorManager()
    mgr.register_worker_class("keycap", KeyCapturingWorker)
    mgr.spawn("user42:myconn", "keycap", {})
    time.sleep(0.5)
    status = mgr.get_status("user42:myconn")
    assert status["state"] == "connected"
    assert status["detail"] == "user42:myconn"
    mgr.stop("user42:myconn")


class HistoryEmittingWorker(ConnectorWorker):
    def connect(self, credentials: dict):
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self): pass
    def fetch_accounts(self): return []
    def fetch_positions(self): return []
    def fetch_balances(self): return []
    def fetch_transactions(self): return []
    def submit_2fa(self, code: str): pass

    def fetch_history_data(self):
        return {"transactions": [], "historical_prices": {}, "account_id": "ACC1"}


def test_fetch_history_data_cmd_emits_history_data_event():
    mgr = ConnectorManager()
    mgr.register_worker_class("hist", HistoryEmittingWorker)
    mgr.spawn("histuser:conn1", "hist", {})
    time.sleep(0.3)
    mgr.send_command("histuser:conn1", {"type": "fetch_history_data"})
    time.sleep(0.5)
    events = mgr.collect_events()
    history_events = [e for e in events if e.get("type") == "history_data"]
    assert len(history_events) == 1
    assert history_events[0]["data"]["account_id"] == "ACC1"
    mgr.stop("histuser:conn1")


class HistoryDataWorker(ConnectorWorker):
    def connect(self, credentials):
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self): pass
    def fetch_accounts(self): return []
    def fetch_positions(self): return []
    def fetch_balances(self): return []
    def fetch_transactions(self): return []
    def submit_2fa(self, c): pass

    def fetch_history_data(self):
        return {
            "account_id": "ACC1",
            "transactions": [
                {"date": "2026-01-02", "kind": "buy", "symbol": "X",
                 "qty": 1.0, "price": 100.0, "amount": -100.0}
            ],
            "historical_prices": {"X": [
                {"date": "2026-01-01", "close": 100.0},
                {"date": "2026-01-02", "close": 100.0},
                {"date": "2026-01-03", "close": 110.0},
            ]},
            "start_date": "2026-01-01",
            "end_date": "2026-01-03",
            "currency": "EUR",
        }


def test_history_data_event_is_persisted_to_db(tmp_path, monkeypatch):
    """Quand un worker émet history_data, manager reconstruit + upsert dans la table."""
    from src.api import deps
    from src.db.engine import create_engine_and_tables
    from src.db.models import portfolio_history_daily
    from sqlalchemy import select

    db_path = tmp_path / "ledger.db"
    test_engine = create_engine_and_tables(db_path)
    monkeypatch.setattr(deps, "get_ledger", lambda user_id: test_engine)

    mgr = ConnectorManager()
    mgr.register_worker_class("histdata", HistoryDataWorker)
    mgr.spawn("user42:histconn", "histdata", {})
    time.sleep(0.3)
    mgr.send_command("user42:histconn", {"type": "fetch_history_data"})
    time.sleep(0.5)
    mgr.collect_events()

    with test_engine.connect() as conn:
        rows = conn.execute(select(portfolio_history_daily)).fetchall()
    assert len(rows) == 3
    dates = sorted(r.date for r in rows)
    assert dates == ["2026-01-01", "2026-01-02", "2026-01-03"]
    mgr.stop("user42:histconn")


def test_worker_handle_stores_connector_type():
    mgr = ConnectorManager()
    mgr.register_worker_class("fake", FakeWorker)
    mgr.spawn("user1:test", "fake", credentials={})
    try:
        assert mgr._workers["user1:test"].connector_type == "fake"
    finally:
        mgr.stop_all()
