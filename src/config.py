from pathlib import Path

DATA_DIR = Path("data")
APP_DB = DATA_DIR / "app.db"
JWT_SECRET_FILE = DATA_DIR / ".jwt_secret"
USERS_DIR = DATA_DIR / "users"
LEDGER_DB = DATA_DIR / "ledger.db"   # legacy, for migration
VAULT_DB = DATA_DIR / "vault.db"     # legacy, for migration
API_HOST = "0.0.0.0"
API_PORT = 8000
