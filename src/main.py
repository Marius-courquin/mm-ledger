from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from src.api import deps
from src.api.router import api_router
from src.config import DATA_DIR
from src.db.engine import create_engine_and_tables
from src.manager import ConnectorManager
from src.vault import Vault


def create_app(data_dir: Path | None = None) -> FastAPI:
    data = data_dir or DATA_DIR

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        deps.vault = Vault(data / "vault.db")
        deps.db_engine = create_engine_and_tables(data / "ledger.db")
        deps.manager = ConnectorManager()
        from src.scheduler import setup_scheduler
        setup_scheduler()
        from src.connectors.woob_bank import WoobWorker
        deps.manager.register_worker_class("woob_bank", WoobWorker)
        from src.connectors.ibkr import IBKRWorker
        deps.manager.register_worker_class("ibkr", IBKRWorker)
        yield
        from src.scheduler import scheduler
        scheduler.shutdown(wait=False)
        deps.manager.stop_all()
        deps.vault.lock()
        if deps.db_engine:
            deps.db_engine.dispose()

    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router)
    return app


app = create_app()
