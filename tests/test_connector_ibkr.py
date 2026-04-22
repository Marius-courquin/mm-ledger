import queue
import socket
from unittest.mock import MagicMock, patch

from src.connectors.ibkr import IBKRWorker


def _make_worker(worker_key: str = "user1:myibkr") -> IBKRWorker:
    # queue.Queue (threading) est fiable en mono-process ; empty() fonctionne sur macOS.
    return IBKRWorker(queue.Queue(), queue.Queue(), {"worker_key": worker_key})


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


def _creds() -> dict:
    return {"username": "charlie", "password": "s3cret", "trading_mode": "live"}


def _patch_connect_dependencies():
    """Return context patching docker, ib_async, socket, time.sleep.

    Yields a dict with 'docker_client', 'container', 'ib'."""
    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        with patch("src.connectors.ibkr.docker") as mock_docker, \
             patch("src.connectors.ibkr.IB") as mock_ib_cls, \
             patch("src.connectors.ibkr.socket.create_connection") as mock_sock, \
             patch("src.connectors.ibkr.time.sleep"):
            client = MagicMock()
            container = MagicMock()
            client.containers.run.return_value = container
            client.containers.get.side_effect = _docker_errors_not_found()
            mock_docker.from_env.return_value = client
            mock_sock.return_value.__enter__.return_value = MagicMock()
            ib = MagicMock()
            mock_ib_cls.return_value = ib
            yield {"docker_client": client, "container": container, "ib": ib, "mock_docker": mock_docker}
    return _ctx()


def _docker_errors_not_found():
    # We need a real docker.errors.NotFound to raise from .get()
    import docker
    return docker.errors.NotFound("not found")


def test_connect_happy_path_emits_connected():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    events = []
    while not w.event_queue.empty():
        events.append(w.event_queue.get())
    states = [e.get("state") for e in events if e.get("type") == "status"]
    assert "starting_gateway" in states
    assert "connected" in states


def test_connect_passes_hardening_flags_to_container():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs["security_opt"] == ["no-new-privileges:true"]
    assert kwargs["mem_limit"] == "2g"
    assert kwargs["nano_cpus"] == 2_000_000_000
    assert kwargs["auto_remove"] is True
    assert kwargs["detach"] is True
    assert kwargs["name"] == "mm-ledger-ibkr-u1-ib"
    # Image digest pinned
    assert kwargs["image"].startswith("ghcr.io/gnzsnz/ib-gateway@sha256:")
    # Env contains creds (expected — they are passed here, not on disk)
    assert kwargs["environment"]["TWS_USERID"] == "charlie"
    assert kwargs["environment"]["TWS_PASSWORD"] == "s3cret"
    assert kwargs["environment"]["TRADING_MODE"] == "live"
    assert kwargs["environment"]["READ_ONLY_API"] == "yes"


def test_connect_dev_mode_publishes_port_on_localhost():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs.get("ports") == {"4001/tcp": ("127.0.0.1", 4001)}


def test_connect_prod_mode_no_port_published():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert "ports" not in kwargs or not kwargs["ports"]


def test_connect_calls_ib_connect_with_correct_endpoint():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    ctx["ib"].connect.assert_called_once_with("127.0.0.1", 4001, clientId=1)


def test_connect_removes_orphan_container_before_spawn():
    w = _make_worker("u1:ib")
    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB"), \
         patch("src.connectors.ibkr.socket.create_connection"), \
         patch("src.connectors.ibkr.time.sleep"):
        client = MagicMock()
        orphan = MagicMock()
        client.containers.get.return_value = orphan
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client
        w.connect(_creds())
        orphan.stop.assert_called_once()
        orphan.remove.assert_called_once_with(force=True)


def test_connect_timeout_emits_error_without_creds():
    w = _make_worker("u1:ib")

    counter = [0]

    def fake_time():
        counter[0] += 100
        return counter[0]

    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB"), \
         patch("src.connectors.ibkr.socket.create_connection", side_effect=OSError("refused")), \
         patch("src.connectors.ibkr.time.sleep"), \
         patch("src.connectors.ibkr.time.time", side_effect=fake_time):
        client = MagicMock()
        client.containers.get.side_effect = _docker_errors_not_found()
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client

        import pytest as _pt
        with _pt.raises(TimeoutError) as excinfo:
            w.connect(_creds())
        msg = str(excinfo.value)
        assert "ib-gateway n'a pas démarré" in msg
        # Anti-leak: aucun credential dans le message d'erreur
        assert "charlie" not in msg
        assert "s3cret" not in msg
