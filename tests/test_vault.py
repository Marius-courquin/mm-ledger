import tempfile
from pathlib import Path

from src.vault import Vault


def test_setup_and_unlock():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        assert v.status == "uninitialized"
        v.setup("testpass")
        assert v.status == "locked"
        assert v.unlock("testpass")
        assert v.status == "unlocked"


def test_wrong_password():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("correct")
        assert not v.unlock("wrong")
        assert v.status == "locked"


def test_store_and_retrieve():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "My TR", {"phone": "+33612345678", "pin": "1234"})
        creds = v.retrieve("tr_1")
        assert creds["phone"] == "+33612345678"
        assert creds["pin"] == "1234"


def test_delete():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.delete("tr_1")
        assert v.retrieve("tr_1") is None


def test_list_connectors():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.store("bp_1", "woob_bank", "BP", {"login": "x"})
        items = v.list_connectors()
        assert len(items) == 2
        assert "phone" not in str(items)


def test_lock():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("pass")
        v.unlock("pass")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.lock()
        assert v.status == "locked"
        assert v.retrieve("tr_1") is None


def test_change_password():
    with tempfile.TemporaryDirectory() as tmp:
        v = Vault(Path(tmp) / "vault.db")
        v.setup("old")
        v.unlock("old")
        v.store("tr_1", "trade_republic", "TR", {"phone": "+33"})
        v.change_password("old", "new")
        v.lock()
        assert not v.unlock("old")
        assert v.unlock("new")
        assert v.retrieve("tr_1")["phone"] == "+33"
