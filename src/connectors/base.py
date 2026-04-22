from abc import ABC, abstractmethod
from multiprocessing import Queue


class ConnectorWorker(ABC):
    def __init__(self, cmd_queue: Queue, event_queue: Queue, config: dict):
        self.cmd_queue = cmd_queue
        self.event_queue = event_queue
        self.config = config

    @abstractmethod
    def connect(self, credentials: dict) -> None: ...

    @abstractmethod
    def disconnect(self) -> None: ...

    @abstractmethod
    def fetch_accounts(self) -> list[dict]: ...

    @abstractmethod
    def fetch_positions(self) -> list[dict]: ...

    @abstractmethod
    def fetch_balances(self) -> list[dict]: ...

    @abstractmethod
    def fetch_transactions(self) -> list[dict]: ...

    @abstractmethod
    def submit_2fa(self, code: str) -> None: ...

    def fetch_history(self) -> list[dict]:
        """Historique journalier de la valeur du portefeuille (base currency).
        Retour : [{date: 'YYYY-MM-DD', value: float}]. [] par défaut — les
        connecteurs qui exposent un historique natif (brokers, via API
        historique du type reqHistoricalData) le surchargent."""
        return []

    def run(self):
        while True:
            cmd = self.cmd_queue.get()
            if cmd["type"] == "shutdown":
                self.disconnect()
                self.event_queue.put({"type": "status", "state": "disconnected"})
                break
            try:
                handler = {
                    "connect": lambda: self.connect(cmd.get("credentials", {})),
                    "disconnect": self.disconnect,
                    "fetch_accounts": self.fetch_accounts,
                    "fetch_positions": self.fetch_positions,
                    "fetch_balances": self.fetch_balances,
                    "fetch_transactions": self.fetch_transactions,
                    "fetch_history": self.fetch_history,
                    "submit_2fa": lambda: self.submit_2fa(cmd["code"]),
                }[cmd["type"]]
                data = handler()
                if data is not None:
                    event_type = cmd["type"].replace("fetch_", "")
                    self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                self.event_queue.put({"type": "error", "message": str(e)})
