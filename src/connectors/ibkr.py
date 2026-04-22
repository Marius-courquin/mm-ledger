import logging
import os
import re
import socket
import time

import docker
import docker.errors
from docker.errors import APIError as DockerAPIError
from docker.errors import NotFound as DockerNotFound
from ib_async import IB

from src.connectors.base import ConnectorWorker

log = logging.getLogger(__name__)

# Pinné par digest pour prévenir une substitution silencieuse (supply chain).
# Digest multi-arch (manifest list) — liste amd64 ET arm64 (Raspberry Pi).
# Résolu via `docker buildx imagetools inspect ghcr.io/gnzsnz/ib-gateway:stable`.
# Upgrade = action manuelle après audit du changelog amont.
IBKR_GATEWAY_IMAGE = "ghcr.io/gnzsnz/ib-gateway@sha256:b248e4dad68cc1de8dd1905ea8598089e92307dfec57f59e08a28182bbb002d5"
IBKR_NETWORK_NAME = "mm-ledger-net"
IBKR_GATEWAY_LIVE_PORT = 4001
IBKR_GATEWAY_PAPER_PORT = 4002
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

    def _gateway_endpoint(self, trading_mode: str) -> tuple[str, int]:
        port = IBKR_GATEWAY_PAPER_PORT if trading_mode == "paper" else IBKR_GATEWAY_LIVE_PORT
        if self._dev_mode():
            return ("127.0.0.1", port)
        return (self._container_name, port)

    # ── contract methods ────────────────────────────────────────────────

    def connect(self, credentials: dict) -> None:
        log.info("IBKR: connector=%s action=connect result=start", self._safe_key())
        self._docker = docker.from_env()

        # 1. Nettoyage d'un éventuel container orphelin
        self._remove_existing_container()

        # 2. Spawn ib-gateway (hardened)
        run_kwargs = dict(
            image=IBKR_GATEWAY_IMAGE,
            name=self._container_name,
            environment={
                "TWS_USERID": credentials["username"],
                "TWS_PASSWORD": credentials["password"],
                "TRADING_MODE": credentials["trading_mode"],
                "READ_ONLY_API": "yes",
                "TWOFA_TIMEOUT_ACTION": "restart",
            },
            detach=True,
            auto_remove=True,
            labels={"mm-ledger": "ibkr-gateway"},
            security_opt=["no-new-privileges:true"],
            mem_limit="2g",
            nano_cpus=2_000_000_000,
            network=IBKR_NETWORK_NAME,
        )
        trading_mode = credentials["trading_mode"]
        gateway_host, gateway_port = self._gateway_endpoint(trading_mode)
        if self._dev_mode():
            run_kwargs["ports"] = {f"{gateway_port}/tcp": ("127.0.0.1", gateway_port)}

        self._container = self._docker.containers.run(**run_kwargs)

        # 3. Poll jusqu'à ce que le port réponde
        self.event_queue.put({"type": "status", "state": "starting_gateway"})
        deadline = time.time() + IBKR_GATEWAY_START_TIMEOUT
        while time.time() < deadline:
            try:
                with socket.create_connection((gateway_host, gateway_port), timeout=2):
                    break
            except OSError:
                time.sleep(2)
        else:
            self._stop_container()
            raise TimeoutError(
                f"ib-gateway n'a pas démarré dans les {IBKR_GATEWAY_START_TIMEOUT}s. "
                f"Consulter 'docker logs {self._container_name}'."
            )

        # 4. Connect ib_async
        self._ib = IB()
        self._ib.connect(gateway_host, gateway_port, clientId=1)
        log.info("IBKR: connector=%s action=connect result=ok", self._safe_key())
        self.event_queue.put({"type": "status", "state": "connected"})

    def _remove_existing_container(self) -> None:
        try:
            old = self._docker.containers.get(self._container_name)
            old.stop(timeout=5)
            old.remove(force=True)
        except DockerNotFound:
            pass

    def _stop_container(self) -> None:
        if self._container is not None:
            try:
                self._container.stop(timeout=10)
            except DockerAPIError:
                pass
            self._container = None

    def disconnect(self) -> None:
        try:
            if self._ib is not None and self._ib.isConnected():
                self._ib.disconnect()
        except Exception:
            pass
        self._ib = None
        self._stop_container()
        log.info("IBKR: connector=%s action=disconnect result=ok", self._safe_key())

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
