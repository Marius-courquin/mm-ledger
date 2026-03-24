import time

from fastapi import APIRouter

from src.api import deps
from src.scheduler import get_job_status, get_scheduler

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
        "scheduler": "running" if (s := get_scheduler()) and s.running else "stopped",
        "workers": workers,
        "db": db_ok,
        "uptime_seconds": int(time.time() - _start_time),
    }


@router.get("/api/scheduler/status")
def scheduler_status():
    return {"jobs": get_job_status()}


@router.get("/api/debug/live-data")
def debug_live_data():
    """Debug: show raw live data cache from workers."""
    import json
    data = deps.manager.get_all_live_data()
    # Truncate large values for readability
    result = {}
    for cid, d in data.items():
        result[cid] = {}
        for key, val in d.items():
            if isinstance(val, (list, dict)):
                s = json.dumps(val)
                result[cid][key] = json.loads(s[:2000]) if len(s) > 2000 else val
            else:
                result[cid][key] = val
    return result
