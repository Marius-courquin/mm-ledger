import queue
import pytest
from multiprocessing import Queue
from src.connectors.base import ConnectorWorker


def drain_queue(q, timeout=0.5):
    """Draine une multiprocessing.Queue de façon fiable (le flush est asynchrone)."""
    events = []
    while True:
        try:
            events.append(q.get(timeout=timeout))
            timeout = 0.1  # plus court pour les suivants
        except Exception:
            break
    return events


class FakeConnector(ConnectorWorker):
    def __init__(self, cmd_q, event_q, config):
        super().__init__(cmd_q, event_q, config)
        self._token = None
        self.connect_called = 0

    def connect(self, credentials):
        self.connect_called += 1
        self._token = "fresh_token"
        self.event_queue.put({"type": "status", "state": "connected"})

    def disconnect(self):
        pass

    def fetch_accounts(self):
        return []

    def fetch_positions(self):
        return []

    def fetch_balances(self):
        return []

    def fetch_transactions(self):
        return []

    def submit_2fa(self, code):
        pass

    def serialize_session(self):
        return {"token": self._token} if self._token else None

    def restore_session(self, blob):
        if blob.get("token") == "valid_token":
            self._token = blob["token"]
            self.event_queue.put({"type": "status", "state": "connected"})
            return True
        return False


def test_connect_with_valid_session_skips_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}, "session_blob": {"token": "valid_token"}})
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 0
    # session_save émis avec le token valide
    events = drain_queue(ev_q)
    save_events = [e for e in events if e["type"] == "session_save"]
    assert len(save_events) == 1
    assert save_events[0]["session"] == {"token": "valid_token"}


def test_connect_with_invalid_session_falls_back_to_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}, "session_blob": {"token": "expired"}})
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 1
    # session_save émis avec le nouveau token frais
    events = drain_queue(ev_q)
    save_events = [e for e in events if e["type"] == "session_save"]
    assert len(save_events) == 1
    assert save_events[0]["session"] == {"token": "fresh_token"}


def test_connect_without_session_does_full_login():
    cmd_q = Queue()
    ev_q = Queue()
    w = FakeConnector(cmd_q, ev_q, {})
    cmd_q.put({"type": "connect", "credentials": {"u": "x"}})  # pas de session_blob
    cmd_q.put({"type": "shutdown"})
    w.run()
    assert w.connect_called == 1
