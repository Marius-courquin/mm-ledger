from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import insert

from src.api import deps
from src.db.models import balance_snapshots

scheduler = AsyncIOScheduler()

_last_results: dict[str, str] = {}


def get_job_status():
    jobs = []
    for job in scheduler.get_jobs():
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

    for cid, state in health.items():
        if state != "connected":
            continue
        try:
            deps.manager.send_command(cid, {"type": "fetch_balances"})
            await asyncio.sleep(2)
            events = deps.manager.collect_events()
            for event in events:
                if event.get("type") == "balances":
                    for bal in event.get("data", []):
                        with deps.db_engine.begin() as conn:
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
            _last_results["daily_snapshot"] = "ok"
        except Exception as e:
            _last_results["daily_snapshot"] = f"error: {e}"


def setup_scheduler():
    scheduler.add_job(daily_snapshot, "cron", hour=23, minute=0, id="daily_snapshot")
    scheduler.start()
