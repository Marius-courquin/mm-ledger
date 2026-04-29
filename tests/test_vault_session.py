import pytest
from src.vault import Vault


@pytest.fixture
def vault(tmp_path):
    v = Vault(tmp_path / "vault.db")
    v.setup("pwd123")
    v.unlock("pwd123")
    v.store("c1", "trade_republic", "TR", {"username": "x"})
    return v


def test_store_and_retrieve_session(vault):
    vault.store_session("c1", {"token": "abc", "refresh": "def"})
    s = vault.retrieve_session("c1")
    assert s == {"token": "abc", "refresh": "def"}


def test_retrieve_session_none_for_unknown(vault):
    assert vault.retrieve_session("nonexistent") is None


def test_retrieve_session_none_when_not_set(vault):
    assert vault.retrieve_session("c1") is None


def test_overwrite_session(vault):
    vault.store_session("c1", {"token": "v1"})
    vault.store_session("c1", {"token": "v2"})
    assert vault.retrieve_session("c1") == {"token": "v2"}


def test_clear_session(vault):
    vault.store_session("c1", {"token": "abc"})
    vault.clear_session("c1")
    assert vault.retrieve_session("c1") is None


def test_session_isolated_per_connector(vault):
    vault.store("c2", "ibkr", "IBKR", {"u": "y"})
    vault.store_session("c1", {"a": 1})
    vault.store_session("c2", {"b": 2})
    assert vault.retrieve_session("c1") == {"a": 1}
    assert vault.retrieve_session("c2") == {"b": 2}


def test_delete_connector_wipes_session(vault):
    vault.store_session("c1", {"x": 1})
    vault.delete("c1")
    # Re-create same id, no session
    vault.store("c1", "trade_republic", "TR", {"username": "x"})
    assert vault.retrieve_session("c1") is None


def test_locked_vault_returns_none(vault, tmp_path):
    vault.lock()
    assert vault.retrieve_session("c1") is None
    vault.store_session("c1", {"a": 1})  # no-op silently
