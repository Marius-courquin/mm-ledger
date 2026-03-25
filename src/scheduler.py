from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import insert

from src.api import deps
from src.db.models import balance_snapshots

_scheduler: AsyncIOScheduler | None = None
_last_results: dict[str, str] = {}


def get_scheduler() -> AsyncIOScheduler | None:
    return _scheduler


def get_job_status():
    if not _scheduler:
        return []
    jobs = []
    for job in _scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "schedule": str(job.trigger),
            "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
            "last_run": None,
            "last_result": _last_results.get(job.id),
        })
    return jobs


async def daily_snapshot():
    """Fetch balances from all connected workers, upsert into balance_snapshots."""
    from datetime import date
    import asyncio
    today = date.today().isoformat()
    health = deps.manager.health_check()

    # Group workers by user_id — composite keys are "user_id:connector_id"
    user_workers: dict[str, list[str]] = {}
    for composite_key, state in health.items():
        if state != "connected":
            continue
        if ":" in composite_key:
            user_id, connector_id = composite_key.split(":", 1)
        else:
            # Legacy key without user prefix
            user_id = None
            connector_id = composite_key
        user_workers.setdefault(user_id, []).append(composite_key)

    for user_id, worker_keys in user_workers.items():
        try:
            if user_id:
                engine = deps.get_ledger(user_id)
            else:
                # Fallback for legacy workers without user prefix
                continue
            for composite_key in worker_keys:
                try:
                    deps.manager.send_command(composite_key, {"type": "fetch_balances"})
                    await asyncio.sleep(2)
                    events = deps.manager.collect_events()
                    for event in events:
                        if event.get("type") == "balances":
                            for bal in event.get("data", []):
                                with engine.begin() as conn:
                                    conn.execute(
                                        insert(balance_snapshots).prefix_with("OR REPLACE").values(
                                            account_id=bal["account_id"],
                                            date=today,
                                            cash=bal.get("cash"),
                                            positions_value=bal.get("positions_value"),
                                            total_value=bal.get("total_value"),
                                            currency=bal.get("currency", "EUR"),
                                            positions=bal.get("positions"),
                                        )
                                    )
                except Exception as e:
                    _last_results["daily_snapshot"] = f"error: {e}"
            _last_results["daily_snapshot"] = "ok"
        except Exception as e:
            _last_results["daily_snapshot"] = f"error: {e}"


def setup_scheduler():
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(daily_snapshot, "cron", hour=23, minute=0, id="daily_snapshot")
    _scheduler.start()


def shutdown_scheduler():
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
    _scheduler = None
