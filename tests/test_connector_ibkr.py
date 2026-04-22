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
        assert w._gateway_endpoint("live") == ("127.0.0.1", 4001)


def test_gateway_endpoint_prod_returns_container_name():
    w = _make_worker("user1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False):
        host, port = w._gateway_endpoint("live")
        assert host == "mm-ledger-ibkr-user1-ib"
        assert port == 4001


def test_gateway_endpoint_paper_mode_returns_port_4002():
    w = _make_worker()
    with patch.object(IBKRWorker, "_dev_mode", return_value=True):
        assert w._gateway_endpoint("paper") == ("127.0.0.1", 4002)


def test_gateway_endpoint_live_mode_returns_port_4001():
    w = _make_worker()
    with patch.object(IBKRWorker, "_dev_mode", return_value=True):
        assert w._gateway_endpoint("live") == ("127.0.0.1", 4001)


def test_connect_paper_mode_uses_port_4002():
    w = _make_worker("u1:ib")
    paper_creds = {"username": "charlie", "password": "s3cret", "trading_mode": "paper"}
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(paper_creds)
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs["ports"] == {"4002/tcp": ("127.0.0.1", 4002)}
    ctx["ib"].connect.assert_called_once_with("127.0.0.1", 4002, clientId=1)


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


def test_connect_dev_mode_publishes_port_on_localhost_without_network():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=True), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert kwargs.get("ports") == {"4001/tcp": ("127.0.0.1", 4001)}
    # En dev, pas de network custom (bridge par défaut) — mm-ledger-net
    # n'existe qu'une fois `docker compose up` lancé, ce qui n'est pas le cas
    # quand on tourne via `./start.sh` en local.
    assert "network" not in kwargs or not kwargs["network"]


def test_connect_prod_mode_no_port_but_internal_network():
    w = _make_worker("u1:ib")
    with patch.object(IBKRWorker, "_dev_mode", return_value=False), \
         _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    kwargs = ctx["docker_client"].containers.run.call_args.kwargs
    assert "ports" not in kwargs or not kwargs["ports"]
    assert kwargs["network"] == "mm-ledger-net"


def test_connect_emits_starting_gateway_before_containers_run():
    """Le user doit voir 'starting_gateway' pendant le premier pull (~minutes)."""
    w = _make_worker("u1:ib")
    call_order = []
    with _patch_connect_dependencies() as ctx:
        def record_run(**kwargs):
            call_order.append("containers.run")
            return MagicMock()

        ctx["docker_client"].containers.run.side_effect = record_run

        # On instrumente event_queue.put pour tracer quand starting_gateway est émis
        original_put = w.event_queue.put

        def trace_put(evt):
            if isinstance(evt, dict) and evt.get("state") == "starting_gateway":
                call_order.append("starting_gateway_emitted")
            original_put(evt)

        w.event_queue.put = trace_put
        w.connect(_creds())

    # starting_gateway doit être émis AVANT containers.run (pour couvrir le pull)
    assert call_order.index("starting_gateway_emitted") < call_order.index("containers.run")


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


def test_disconnect_stops_ib_and_container():
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as ctx:
        w.connect(_creds())
    w.disconnect()
    ctx["ib"].disconnect.assert_called_once()
    ctx["container"].stop.assert_called_once()


def test_disconnect_idempotent_when_never_connected():
    w = _make_worker("u1:ib")
    # Pas de connect avant
    w.disconnect()  # Ne doit pas lever


def test_connect_logs_audit_event_without_creds(caplog):
    import logging as _log
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as _ctx:
        with caplog.at_level(_log.INFO, logger="src.connectors.ibkr"):
            w.connect(_creds())
    audit_lines = [r.getMessage() for r in caplog.records if "IBKR" in r.getMessage()]
    assert any("action=connect" in line for line in audit_lines)
    # Anti-leak
    for line in audit_lines:
        assert "charlie" not in line
        assert "s3cret" not in line


def test_disconnect_logs_audit_event(caplog):
    import logging as _log
    w = _make_worker("u1:ib")
    with _patch_connect_dependencies() as _ctx:
        w.connect(_creds())
    with caplog.at_level(_log.INFO, logger="src.connectors.ibkr"):
        w.disconnect()
    audit_lines = [r.getMessage() for r in caplog.records if "IBKR" in r.getMessage()]
    assert any("action=disconnect" in line for line in audit_lines)


def test_connect_bad_creds_error_does_not_leak():
    w = _make_worker("u1:ib")
    with patch("src.connectors.ibkr.docker") as mock_docker, \
         patch("src.connectors.ibkr.IB") as mock_ib_cls, \
         patch("src.connectors.ibkr.socket.create_connection"), \
         patch("src.connectors.ibkr.time.sleep"):
        client = MagicMock()
        client.containers.get.side_effect = _docker_errors_not_found()
        client.containers.run.return_value = MagicMock()
        mock_docker.from_env.return_value = client
        ib = MagicMock()
        ib.connect.side_effect = ConnectionError("auth failed")
        mock_ib_cls.return_value = ib

        import pytest as _pt
        with _pt.raises(ConnectionError) as excinfo:
            w.connect(_creds())
        msg = str(excinfo.value)
        assert "charlie" not in msg
        assert "s3cret" not in msg
