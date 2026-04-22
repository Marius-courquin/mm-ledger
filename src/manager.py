import time
from dataclasses import dataclass, field
from multiprocessing import Process, Queue


def _run_worker(cls, cmd_q, event_q):
    """Module-level target so it can be pickled by the spawn start method."""
    worker = cls(cmd_q, event_q, {})
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

        proc = Process(target=_run_worker, args=(cls, cmd_q, event_q), daemon=True)
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
