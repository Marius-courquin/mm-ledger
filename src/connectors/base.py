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

    def fetch_history_data(self) -> dict:
        """Retourne {transactions, historical_prices, account_id, start_date, end_date, currency}.
        Défaut vide — overridable par les connecteurs qui exposent executions + prix historiques."""
        return {"transactions": [], "historical_prices": {}, "account_id": ""}

    # --- Persistance de session (override par connecteur) ---

    def serialize_session(self) -> dict | None:
        """Override pour exporter l'état d'auth courant. None = ne rien persister."""
        return None

    def restore_session(self, blob: dict) -> bool:
        """Override pour réinjecter un blob de session.
        Doit pinger un endpoint léger pour valider.
        Renvoie True si la session a été restaurée et est valide, False sinon."""
        return False

    def _emit_session_save(self):
        """Helper pour pousser un event de sauvegarde de session vers le manager."""
        blob = None
        try:
            blob = self.serialize_session()
        except Exception as e:
            self.event_queue.put({"type": "error", "message": f"serialize_session failed: {e}"})
            return
        if blob is not None:
            self.event_queue.put({"type": "session_save", "session": blob})

    def run(self):
        while True:
            cmd = self.cmd_queue.get()
            if cmd["type"] == "shutdown":
                self.disconnect()
                self.event_queue.put({"type": "status", "state": "disconnected"})
                break
            try:
                if cmd["type"] == "connect":
                    creds = cmd.get("credentials", {})
                    session_blob = cmd.get("session_blob")
                    restored = False
                    if session_blob:
                        try:
                            restored = self.restore_session(session_blob)
                        except Exception:
                            restored = False
                    if not restored:
                        self.connect(creds)
                    # Persiste la session courante après connect réussi
                    self._emit_session_save()
                    continue
                if cmd["type"] == "save_session":
                    self._emit_session_save()
                    continue
                handler = {
                    "disconnect": self.disconnect,
                    "fetch_accounts": self.fetch_accounts,
                    "fetch_positions": self.fetch_positions,
                    "fetch_balances": self.fetch_balances,
                    "fetch_transactions": self.fetch_transactions,
                    "fetch_history_data": self.fetch_history_data,
                    "submit_2fa": lambda: self.submit_2fa(cmd["code"]),
                }[cmd["type"]]
                data = handler()
                if data is not None:
                    event_type = cmd["type"].replace("fetch_", "")
                    self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                self.event_queue.put({"type": "error", "message": str(e)})
