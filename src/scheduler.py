from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import insert

from src.api import deps
from src.db.models import balance_snapshots, net_worth_snapshots

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

    # Net worth snapshot per user
    for user_id, worker_keys in user_workers.items():
        if not user_id:
            continue
        try:
            user_live = deps.manager.get_user_live_data(user_id)
            bank_total = 0.0
            investments_total = 0.0
            breakdown = []

            for cid, data in user_live.items():
                for b in data.get("balances", []):
                    if not isinstance(b, dict):
                        continue
                    amount = float(b.get("amount", 0) or b.get("total_value", 0))
                    name = b.get("label") or b.get("name") or cid
                    has_positions = bool(data.get("positions"))
                    if has_positions:
                        investments_total += amount
                        breakdown.append({"name": f"Espèces {name}", "value": amount, "type": "investment"})
                    else:
                        bank_total += amount
                        breakdown.append({"name": name, "value": amount, "type": "bank"})

                raw_positions = data.get("positions", [])
                if isinstance(raw_positions, list):
                    for acc_data in raw_positions:
                        if not isinstance(acc_data, dict):
                            continue
                        acc_label = acc_data.get("label", cid)
                        acc_value = 0.0
                        for cat in acc_data.get("categories", []):
                            for pos in cat.get("positions", []):
                                cur_raw = pos.get("currentPrice") or pos.get("current_price")
                                cur = float(cur_raw) if cur_raw else 0
                                qty = float(pos.get("netSize", 0) or pos.get("quantity", 0))
                                if cur > 0:
                                    acc_value += qty * cur
                        if acc_value > 0:
                            investments_total += acc_value
                            breakdown.append({"name": acc_label, "value": acc_value, "type": "investment"})

            total = bank_total + investments_total
            engine = deps.get_ledger(user_id)
            with engine.begin() as conn:
                conn.execute(
                    insert(net_worth_snapshots).prefix_with("OR REPLACE").values(
                        date=today,
                        total=total,
                        bank_total=bank_total,
                        investments_total=investments_total,
                        breakdown=breakdown,
                    )
                )
        except Exception as e:
            _last_results["daily_snapshot"] = f"net_worth error ({user_id}): {e}"


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
