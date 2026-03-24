import time

from fastapi import APIRouter

from src.api import deps
from src.scheduler import get_job_status, scheduler

router = APIRouter(tags=["system"])

_start_time = time.time()


@router.get("/api/health")
def health():
    workers = deps.manager.health_check() if deps.manager else {}
    db_ok = "ok"
    try:
        with deps.db_engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
    except Exception:
        db_ok = "error"
    return {
        "status": "ok" if db_ok == "ok" else "degraded",
        "vault": deps.vault.status if deps.vault else "uninitialized",
        "scheduler": "running" if scheduler.running else "stopped",
        "workers": workers,
        "db": db_ok,
        "uptime_seconds": int(time.time() - _start_time),
    }


@router.get("/api/scheduler/status")
def scheduler_status():
    return {"jobs": get_job_status()}
