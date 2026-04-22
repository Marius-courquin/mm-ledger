import logging
import os
import re

from src.connectors.base import ConnectorWorker

log = logging.getLogger(__name__)

# Pinné par digest pour prévenir une substitution silencieuse (supply chain).
# Digest multi-arch (manifest list) — liste amd64 ET arm64 (Raspberry Pi).
# Résolu via `docker buildx imagetools inspect ghcr.io/gnzsnz/ib-gateway:stable`.
# Upgrade = action manuelle après audit du changelog amont.
IBKR_GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway@sha256:b248e4dad68cc1de8dd1905ea8598089e92307dfec57f59e08a28182bbb002d5"
IBKR_NETWORK_NAME = "mm-ledger-net"
IBKR_GATEWAY_PORT = 4001
IBKR_GATEWAY_START_TIMEOUT = 90  # seconds


class IBKRWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._ib = None
        self._container = None
        self._docker = None

    # ── helpers ──────────────────────────────────────────────────────────

    def _safe_key(self) -> str:
        # docker container names: [a-zA-Z0-9][a-zA-Z0-9_.-]*, max 63 chars
        raw = self.config.get("worker_key", "default").lower()
        return re.sub(r"[^a-z0-9_.-]", "-", raw)[:50]

    @property
    def _container_name(self) -> str:
        return f"mm-ledger-ibkr-{self._safe_key()}"

    def _dev_mode(self) -> bool:
        # App runs inside docker if /.dockerenv exists.
        return not os.path.exists("/.dockerenv")

    def _gateway_endpoint(self) -> tuple[str, int]:
        if self._dev_mode():
            return ("127.0.0.1", IBKR_GATEWAY_PORT)
        return (self._container_name, IBKR_GATEWAY_PORT)

    # ── contract methods ────────────────────────────────────────────────

    def connect(self, credentials: dict) -> None:
        raise NotImplementedError  # Task 7

    def disconnect(self) -> None:
        raise NotImplementedError  # Task 9

    def fetch_accounts(self) -> list[dict]:
        if not self._ib:
            return []
        return [{"id": a, "name": a, "type": "margin"} for a in self._ib.managedAccounts()]

    def fetch_positions(self) -> list[dict]:
        if not self._ib:
            return []
        return [
            {
                "account_id": p.account,
                "instrument": str(p.contract.conId),
                "symbol": p.contract.symbol,
                "category": p.contract.secType.lower(),
                "quantity": float(p.position),
                "avg_price": float(p.avgCost),
                "currency": p.contract.currency,
            }
            for p in self._ib.positions()
        ]

    def fetch_balances(self) -> list[dict]:
        if not self._ib:
            return []
        out = []
        for acc in self._ib.managedAccounts():
            values = self._ib.accountValues(acc)
            net_liq = next((v.value for v in values if v.tag == "NetLiquidation"), 0)
            cash = next((v.value for v in values if v.tag == "TotalCashBalance"), 0)
            currency = next((v.currency for v in values if v.tag == "NetLiquidation"), "EUR")
            out.append({
                "account_id": acc,
                "cash": float(cash),
                "total_value": float(net_liq),
                "positions_value": float(net_liq) - float(cash),
                "currency": currency,
            })
        return out

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str) -> None:
        pass
