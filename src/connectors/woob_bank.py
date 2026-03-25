import logging
import shutil
import sys
from pathlib import Path

from src.connectors.base import ConnectorWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", stream=sys.stderr)
log = logging.getLogger("woob_worker")


class WoobWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._backend = None
        self._woob = None

    def _apply_patches(self):
        patches_dir = Path(__file__).parent.parent / "patches" / "woob_banquepopulaire"
        if not patches_dir.exists():
            log.info("No patches to apply")
            return
        target = Path.home() / ".local/share/woob/modules/3.7/woob_modules/banquepopulaire"
        target.mkdir(parents=True, exist_ok=True)
        for f in patches_dir.glob("*.py"):
            shutil.copy2(f, target / f.name)
            log.info(f"Patched {f.name}")

    def connect(self, credentials: dict):
        self.event_queue.put({"type": "status", "state": "connecting"})
        try:
            from woob.core import Woob
            from woob.exceptions import AppValidation, SentOTPQuestion

            log.info("Applying patches...")
            self._apply_patches()

            module = credentials.get("bank_module", "banquepopulaire")
            log.info(f"Loading Woob backend: {module}")
            self._woob = Woob()
            params = {
                "login": credentials["login"],
                "password": credentials["password"],
                "request_information": "interactive",
            }
            if credentials.get("region"):
                params["cdetab"] = credentials["region"]

            self._woob.load_backend(module, "bank", params=params)
            self._backend = self._woob["bank"]

            log.info("Fetching accounts (may trigger 2FA)...")
            try:
                accs = list(self._backend.iter_accounts())
                log.info(f"Connected — {len(accs)} accounts found")
                self.event_queue.put({"type": "status", "state": "connected"})
                accs_data = [
                    {"id": a.id, "name": a.label, "balance": float(a.balance),
                     "currency": a.currency_text, "type": str(a.type)} for a in accs
                ]
                self.event_queue.put({"type": "accounts", "data": accs_data})
                # Also send balances so the dashboard shows them
                self.event_queue.put({"type": "balances", "data": [
                    {"account_id": a.id, "amount": float(a.balance),
                     "currencyId": a.currency_text, "total_value": float(a.balance)} for a in accs
                ]})
            except SentOTPQuestion as e:
                log.info(f"2FA SMS required: {e.message}")
                self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message), "method": "sms"})
            except AppValidation as e:
                log.info(f"2FA App required: {e.message}")
                self.event_queue.put({"type": "status", "state": "waiting_2fa", "detail": str(e.message), "method": "app"})

        except Exception as e:
            log.error(f"Connect failed: {e}", exc_info=True)
            self.event_queue.put({"type": "error", "message": str(e)})

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
        log.info(f"Submitting 2FA code...")
        try:
            self._backend.config["code_sms"].set(code)
        except Exception:
            self._backend.config["resume"].set("ok")
        try:
            accs = list(self._backend.iter_accounts())
            log.info(f"2FA success — {len(accs)} accounts")
            self.event_queue.put({"type": "status", "state": "connected"})
            self.event_queue.put({
                "type": "accounts", "data": [
                    {"id": a.id, "name": a.label, "balance": float(a.balance)} for a in accs
                ],
            })
        except Exception as e:
            log.error(f"2FA failed: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})
