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
        for handle in self._workers.values():
            while not handle.event_queue.empty():
                try:
                    event = handle.event_queue.get_nowait()
                    if event.get("type") == "status":
                        handle.state = event.get("state", handle.state)
                        handle.detail = event.get("detail")
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
