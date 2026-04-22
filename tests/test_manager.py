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
