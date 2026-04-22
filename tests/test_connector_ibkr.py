from multiprocessing import Queue
from unittest.mock import patch

from src.connectors.ibkr import IBKRWorker


def _make_worker(worker_key: str = "user1:myibkr") -> IBKRWorker:
    return IBKRWorker(Queue(), Queue(), {"worker_key": worker_key})


def test_safe_key_sanitises_colons_and_special_chars():
    w = _make_worker("User42:My_Conn!")
    assert w._safe_key() == "user42-my_conn-"


def test_safe_key_truncates_to_50_chars():
    w = _make_worker("a" * 80)
    assert len(w._safe_key()) == 50


def test_dev_mode_true_when_no_dockerenv():
    w = _make_worker()
    with patch("os.path.exists", return_value=False):
        assert w._dev_mode() is True


def test_dev_mode_false_when_dockerenv_exists():
    w = _make_worker()
    with patch("os.path.exists", return_value=True):
        assert w._dev_mode() is False


def test_gateway_endpoint_dev_returns_localhost():
    w = _make_worker()
    with patch.object(IBKRWorker, "_dev_mode", return_value=True):
        assert w._gateway_endpoint() == ("127.0.0.1", 4001)


def test_gateway_endpoint_prod_returns_container_name():
    w = _make_worker("user1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False):
        host, port = w._gateway_endpoint()
        assert host == "mm-ledger-ibkr-user1-ib"
        assert port == 4001
