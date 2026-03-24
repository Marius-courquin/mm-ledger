import shutil
from pathlib import Path

from src.connectors.base import ConnectorWorker


class WoobWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._backend = None
        self._woob = None

    def _apply_patches(self):
        patches_dir = Path(__file__).parent.parent / "patches" / "woob_banquepopulaire"
        if not patches_dir.exists():
            return
        target = Path.home() / ".local/share/woob/modules/3.7/woob_modules/banquepopulaire"
        target.mkdir(parents=True, exist_ok=True)
        for f in patches_dir.glob("*.py"):
            shutil.copy2(f, target / f.name)

    def connect(self, credentials: dict):
        from woob.core import Woob
        from woob.exceptions import AppValidation, SentOTPQuestion

        self._apply_patches()
        self._woob = Woob()
        module = credentials.get("bank_module", "banquepopulaire")
        params = {
            "login": credentials["login"],
            "password": credentials["password"],
            "request_information": "interactive",
        }
        if credentials.get("region"):
            params["cdetab"] = credentials["region"]

        self._woob.load_backend(module, "bank", params=params)
        self._backend = self._woob["bank"]

        try:
            accs = list(self._backend.iter_accounts())
            self.event_queue.put({"type": "status", "state": "connected"})
            self.event_queue.put({
                "type": "accounts", "data": [
                    {"id": a.id, "name": a.label, "balance": float(a.balance),
                     "currency": a.currency_text, "type": str(a.type)} for a in accs
                ],
            })
        except SentOTPQuestion as e:
            self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message)})
        except AppValidation as e:
            self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message)})

    def disconnect(self):
        self._backend = None
        self._woob = None

    def fetch_accounts(self) -> list[dict]:
        if not self._backend:
            return []
        accs = list(self._backend.iter_accounts())
        return [{"id": a.id, "name": a.label, "balance": float(a.balance),
                 "currency": a.currency_text, "type": str(a.type)} for a in accs]

    def fetch_positions(self) -> list[dict]:
        return []

    def fetch_balances(self) -> list[dict]:
        if not self._backend:
            return []
        accs = list(self._backend.iter_accounts())
        return [{"account_id": a.id, "cash": float(a.balance),
                 "total_value": float(a.balance), "currency": a.currency_text} for a in accs]

    def fetch_transactions(self) -> list[dict]:
        if not self._backend:
            return []
        result = []
        for acc in self._backend.iter_accounts():
            for tr in self._backend.iter_history(acc):
                result.append({
                    "account_id": acc.id, "date": tr.date.isoformat(),
                    "label": tr.label, "amount": float(tr.amount), "type": str(tr.type),
                })
        return result

    def submit_2fa(self, code: str):
        if not self._backend:
            return
        try:
            self._backend.config["code_sms"].set(code)
        except Exception:
            self._backend.config["resume"].set("ok")
        try:
            accs = list(self._backend.iter_accounts())
            self.event_queue.put({"type": "status", "state": "connected"})
            self.event_queue.put({
                "type": "accounts", "data": [
                    {"id": a.id, "name": a.label, "balance": float(a.balance)} for a in accs
                ],
            })
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})
