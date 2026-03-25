from pathlib import Path
from src.vault import Vault
from src.manager import ConnectorManager
from src.db.engine import create_engine_and_tables
from src.config import USERS_DIR

app_db = None
jwt_secret: str = ""
manager: ConnectorManager | None = None
users_dir: Path = USERS_DIR

# Legacy single-user compat (used by existing routes until Task 4 scopes them)
vault = None
db_engine = None

_user_vaults: dict[str, Vault] = {}
_user_engines: dict[str, object] = {}


def get_vault(user_id: str) -> Vault:
    if user_id not in _user_vaults:
        path = users_dir / user_id / "vault.db"
        _user_vaults[user_id] = Vault(path)
    return _user_vaults[user_id]


def get_ledger(user_id: str):
    if user_id not in _user_engines:
        path = users_dir / user_id / "ledger.db"
        _user_engines[user_id] = create_engine_and_tables(path)
    return _user_engines[user_id]


def cleanup_user(user_id: str):
    if user_id in _user_vaults:
        _user_vaults[user_id].lock()
        del _user_vaults[user_id]
    if user_id in _user_engines:
        _user_engines[user_id].dispose()
        del _user_engines[user_id]
