import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from src.api import deps
from src.api.router import api_router
from src.config import DATA_DIR, APP_DB, JWT_SECRET_FILE
from src.db.app_db import create_app_db
from src.auth import get_or_create_jwt_secret
from src.api.middleware import set_jwt_secret
from src.manager import ConnectorManager


def create_app(data_dir: Path | None = None) -> FastAPI:
    data = data_dir or DATA_DIR

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Init app.db
        app_db_path = data / "app.db" if data != DATA_DIR else APP_DB
        deps.app_db = create_app_db(app_db_path)

        # Init JWT secret
        jwt_path = data / ".jwt_secret" if data != DATA_DIR else JWT_SECRET_FILE
        deps.jwt_secret = get_or_create_jwt_secret(jwt_path)
        set_jwt_secret(deps.jwt_secret)

        # Set users_dir for per-user data
        deps.users_dir = data / "users"

        # Manager + connectors
        deps.manager = ConnectorManager()
        from src.scheduler import setup_scheduler, shutdown_scheduler
        setup_scheduler()
        from src.connectors.woob_bank import WoobWorker
        deps.manager.register_worker_class("woob_bank", WoobWorker)
        from src.connectors.ibkr import IBKRWorker
        deps.manager.register_worker_class("ibkr", IBKRWorker)
        from src.connectors.trade_republic import TradeRepublicWorker
        deps.manager.register_worker_class("trade_republic", TradeRepublicWorker)
        yield
        shutdown_scheduler()
        deps.manager.stop_all()

    app = FastAPI(lifespan=lifespan)
    app.include_router(api_router)

    # Serve frontend static files in production (built by Dockerfile)
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse

        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            file_path = static_dir / full_path
            if file_path.is_file():
                return FileResponse(file_path)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app()
