import time
from dataclasses import dataclass, field
from multiprocessing import Process, Queue


def _run_worker(cls, cmd_q, event_q, config):
    """Module-level target so it can be pickled by the spawn start method."""
    # Configure logging in the child process — sans ça, les log.info des workers
    # disparaissent (le process fils n'hérite pas des handlers du parent).
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    worker = cls(cmd_q, event_q, config)
    worker.run()


@dataclass
class WorkerHandle:
    process: Process
    cmd_queue: Queue
    event_queue: Queue
    state: str = "connecting"
    detail: str | None = None
    started_at: float = field(default_factory=time.time)


class ConnectorManager:
    def __init__(self):
        self._workers: dict[str, WorkerHandle] = {}
        self._worker_classes: dict[str, type] = {}
        # Live data cache — populated from worker events
        self.live_data: dict[str, dict] = {}  # connector_id -> {accounts, balances, positions}

    def register_worker_class(self, connector_type: str, cls: type):
        self._worker_classes[connector_type] = cls

    def spawn(self, connector_id: str, connector_type: str, credentials: dict):
        if connector_id in self._workers:
            self.stop(connector_id)

        cmd_q = Queue()
        event_q = Queue()
        cls = self._worker_classes[connector_type]

        proc = Process(
            target=_run_worker,
            args=(cls, cmd_q, event_q, {"worker_key": connector_id}),
            daemon=True,
        )
        proc.start()
        handle = WorkerHandle(process=proc, cmd_queue=cmd_q, event_queue=event_q)
        self._workers[connector_id] = handle
        self.live_data[connector_id] = {"accounts": [], "balances": [], "positions": [], "transactions": []}
        cmd_q.put({"type": "connect", "credentials": credentials})

    def stop(self, connector_id: str):
        handle = self._workers.get(connector_id)
        if not handle:
            return
        handle.cmd_queue.put({"type": "shutdown"})
        handle.process.join(timeout=5)
        if handle.process.is_alive():
            handle.process.terminate()
        handle.state = "disconnected"

    def stop_all(self):
        for cid in list(self._workers):
            self.stop(cid)

    def send_command(self, connector_id: str, cmd: dict):
        handle = self._workers.get(connector_id)
        if handle and handle.process.is_alive():
            handle.cmd_queue.put(cmd)

    def collect_events(self) -> list[dict]:
        events = []
        for cid, handle in self._workers.items():
            while not handle.event_queue.empty():
                try:
                    event = handle.event_queue.get_nowait()
                    event["connector_id"] = cid
                    evt_type = event.get("type")

                    if evt_type == "status":
                        handle.state = event.get("state", handle.state)
                        handle.detail = event.get("detail")
                    elif evt_type == "error":
                        handle.state = "error"
                        handle.detail = event.get("message")
                    elif evt_type == "history_data":
                        self._persist_history_for_worker(cid, event.get("data", {}))
                    elif evt_type in ("accounts", "balances", "positions", "transactions"):
                        # Cache live data
                        if cid not in self.live_data:
                            self.live_data[cid] = {"accounts": [], "balances": [], "positions": [], "transactions": []}
                        self.live_data[cid][evt_type] = event.get("data", [])

                    events.append(event)
                except Exception:
                    break
        return events

    def get_status(self, connector_id: str) -> dict:
        handle = self._workers.get(connector_id)
        if not handle:
            return {"state": "disconnected"}
        self.collect_events()
        return {
            "state": handle.state,
            "pid": handle.process.pid if handle.process.is_alive() else None,
            "uptime_seconds": time.time() - handle.started_at if handle.process.is_alive() else None,
            "detail": handle.detail,
        }

    def health_check(self) -> dict[str, str]:
        self.collect_events()
        return {cid: h.state for cid, h in self._workers.items()}

    def get_all_live_data(self) -> dict[str, dict]:
        """Drain events and return all cached live data."""
        self.collect_events()
        return self.live_data

    def stop_user_workers(self, user_id: str):
        """Stop all workers belonging to a user."""
        for cid in list(self._workers):
            if cid.startswith(f"{user_id}:"):
                self.stop(cid)

    def get_user_live_data(self, user_id: str) -> dict:
        """Return only live data for the given user's workers."""
        self.collect_events()
        prefix = f"{user_id}:"
        return {k[len(prefix):]: v for k, v in self.live_data.items() if k.startswith(prefix)}

    def get_user_health(self, user_id: str) -> dict[str, str]:
        """Return health of user's workers only."""
        self.collect_events()
        prefix = f"{user_id}:"
        return {k[len(prefix):]: h.state for k, h in self._workers.items() if k.startswith(prefix)}

    def _persist_history_for_worker(self, composite_key: str, data: dict) -> None:
        """Reconstruit la timeline depuis data et upsert dans portfolio_history_daily."""
        if ":" not in composite_key:
            return
        user_id, connector_id = composite_key.split(":", 1)
        account_id = data.get("account_id") or connector_id
        raw_txs = data.get("transactions", [])
        historical_prices = data.get("historical_prices", {})
        start = data.get("start_date")
        end = data.get("end_date")
        currency = data.get("currency", "EUR")
        if not start or not end:
            return

        from src.performance import reconstruct_timeline, TxEvent
        tx_events = [
            TxEvent(
                date=t["date"], kind=t["kind"],
                symbol=t.get("symbol"),
                qty=float(t.get("qty", 0.0)),
                price=float(t.get("price", 0.0)),
                amount=float(t.get("amount", 0.0)),
            )
            for t in raw_txs
        ]
        current_cash = data.get("current_cash")
        current_positions = data.get("current_positions")
        timeline = reconstruct_timeline(
            tx_events, historical_prices,
            start_date=start, end_date=end,
            current_cash=current_cash,
            current_positions=current_positions,
        )

        if not timeline:
            return

        from src.api import deps
        from src.db.models import portfolio_history_daily
        from sqlalchemy import insert
        engine = deps.get_ledger(user_id)
        with engine.begin() as conn:
            for pt in timeline:
                conn.execute(
                    insert(portfolio_history_daily).prefix_with("OR REPLACE").values(
                        connector_id=connector_id,
                        account_id=account_id,
                        date=pt["date"],
                        total_value=pt["total_value"],
                        cash=pt["cash"],
                        positions_value=pt["positions_value"],
                        cash_flow_external=pt["cash_flow_external"],
                        currency=currency,
                    )
                )
