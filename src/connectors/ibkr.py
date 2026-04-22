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
IBKR_GATEWAY_START_TIMEOUT = 90  # seconds — port ouvert par le Java
IBKR_API_AUTH_TIMEOUT = 180       # seconds — ib_async handshake (2FA inclus)
IBKR_API_RETRY_DELAY = 5          # seconds entre 2 tentatives IB.connect()


def _base_value(values, tag: str, default: float = 0.0) -> float:
    """Extrait un tag d'accountValues en filtrant sur currency=BASE quand possible,
    sinon prend la première occurrence. Les accountValues d'IBKR retournent une ligne
    par (tag, currency) ; la currency='BASE' est la valeur agrégée en monnaie de base."""
    base = next((v.value for v in values if v.tag == tag and v.currency == "BASE"), None)
    if base is not None:
        try:
            return float(base)
        except (TypeError, ValueError):
            return default
    any_val = next((v.value for v in values if v.tag == tag), None)
    if any_val is not None:
        try:
            return float(any_val)
        except (TypeError, ValueError):
            return default
    return default


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
        # Émis AVANT le spawn pour couvrir le premier pull d'image (peut durer plusieurs minutes).
        self.event_queue.put({"type": "status", "state": "starting_gateway"})
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
        )
        trading_mode = credentials["trading_mode"]
        gateway_host, gateway_port = self._gateway_endpoint(trading_mode)
        if self._dev_mode():
            # Dev : network_mode=host. Raison : IBC configure TrustedIPs=127.0.0.1 par
            # défaut. En bridge docker, la source IP vue par ib-gateway serait l'IP du
            # bridge (172.x), rejetée au niveau applicatif → timeout silencieux sur le
            # handshake ib_async. En host mode, le container partage la stack réseau de
            # l'hôte → la source reste 127.0.0.1, acceptée.
            run_kwargs["network_mode"] = "host"
        else:
            # Prod : network docker dédié, aucun port publié sur l'hôte. ib-gateway
            # acceptera les connexions depuis le même network via TRUSTED_IPS (widened).
            run_kwargs["network"] = IBKR_NETWORK_NAME
            run_kwargs["environment"]["TRUSTED_IPS"] = "0.0.0.0"

        self._container = self._docker.containers.run(**run_kwargs)

        # 3. Poll jusqu'à ce que le port réponde
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

        # 4. Connect ib_async (retry : le handshake peut échouer tant que la 2FA mobile
        #    n'est pas validée ou que IBC n'est pas prêt).
        # Note : on ne passe PAS en state="waiting_2fa" ici — ce state affiche une modal
        # de saisie code dans le front (pour Trade Republic). Pour IBKR le 2FA est mobile.
        self._ib = IB()
        auth_deadline = time.time() + IBKR_API_AUTH_TIMEOUT
        last_err: Exception | None = None
        while time.time() < auth_deadline:
            try:
                self._ib.connect(gateway_host, gateway_port, clientId=1, timeout=10)
                break
            except Exception as e:
                last_err = e
                time.sleep(IBKR_API_RETRY_DELAY)
        else:
            self._stop_container()
            raise TimeoutError(
                f"ib_async n'a pas pu s'authentifier après {IBKR_API_AUTH_TIMEOUT}s. "
                f"Vérifier l'approbation 2FA sur mobile ou les credentials IBKR."
            )

        log.info("IBKR: connector=%s action=connect result=ok", self._safe_key())
        self.event_queue.put({"type": "status", "state": "connected"})

        # 5. Fetch initial (accounts/balances/positions) pour peupler le live_data.
        # IBKR n'a pas de WebSocket push — contrairement à TR — donc on déclenche
        # explicitement les fetches après connect. Les échecs individuels sont loggés
        # mais ne font pas échouer la connexion (le scheduler re-tentera à 23h).
        # ib.sleep(5) laisse à ib_async le temps de recevoir managedAccounts(),
        # accountValues() et positions() du serveur IBKR (3-5s typiquement).
        self._ib.sleep(5)
        self._fetch_and_emit_initial()

    def _fetch_and_emit_initial(self) -> None:
        for fetch_name in ("fetch_accounts", "fetch_balances", "fetch_positions"):
            try:
                data = getattr(self, fetch_name)()
                event_type = fetch_name.replace("fetch_", "")
                log.info(
                    "IBKR: connector=%s action=%s count=%d",
                    self._safe_key(), fetch_name, len(data),
                )
                self.event_queue.put({"type": event_type, "data": data})
            except Exception as e:
                log.warning(
                    "IBKR: connector=%s action=%s result=error err=%s",
                    self._safe_key(), fetch_name, type(e).__name__,
                )

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
        """Format TR-compatible : une entrée par compte IBKR, avec les positions
        regroupées sous une catégorie 'stocksAndETFs'. Permet au endpoint
        /api/portfolio (code TR-centric) de consommer les données directement.

        Les prix (avgCost, marketPrice) arrivent d'IBKR dans la currency native du
        contrat (ex. USD pour actions US). On les convertit en BASE currency du
        compte pour que le front affiche tout de manière cohérente en EUR. Taux
        via tag ExchangeRate d'IBKR, fallback sur ratio StockMarketValue/BASE."""
        if not self._ib:
            return []
        positions = self._ib.positions()
        portfolio_items = self._ib.portfolio()
        pf_by = {p.contract.conId: p for p in portfolio_items}

        fx_to_base, base_currency = self._fx_to_base()
        log.info(
            "IBKR: positions raw_count=%d portfolio_count=%d fx_to_base=%s base=%s",
            len(positions), len(portfolio_items), fx_to_base, base_currency,
        )

        by_account: dict[str, list[dict]] = {}
        for p in positions:
            pf = pf_by.get(p.contract.conId)
            native_price = float(pf.marketPrice) if pf and pf.marketPrice else None
            native_cost = float(p.avgCost) if p.avgCost else 0.0
            rate = fx_to_base.get(p.contract.currency, 1.0)
            by_account.setdefault(p.account, []).append({
                "isin": str(p.contract.conId),
                "name": p.contract.symbol,
                "shortName": p.contract.symbol,
                "netSize": float(p.position),
                "averageBuyIn": native_cost * rate,
                "currentPrice": native_price * rate if native_price is not None else None,
                "currencyId": base_currency,
            })

        return [
            {
                "secAccNo": acc,
                "productType": "DEFAULT",
                "label": f"IBKR {acc}",
                "categories": [{
                    "categoryType": "stocksAndETFs",
                    "positions": pos_list,
                }],
            }
            for acc, pos_list in by_account.items()
        ]

    def _fx_to_base(self) -> tuple[dict[str, float], str]:
        """Retourne (currency → multiplicateur vers BASE, label de la BASE currency).

        Stratégie :
        1. Tag ExchangeRate d'IBKR : valeur = "amount of currency per 1 BASE"
           → inverse = multiplicateur pour currency → BASE.
        2. Fallback : ratio StockMarketValue(BASE) / StockMarketValue(currency)
           sur les comptes où des stocks existent dans cette currency.
        """
        accounts = self._ib.managedAccounts()
        if not accounts:
            return {}, "EUR"
        values = self._ib.accountValues(accounts[0])
        base_currency = (
            next((v.value for v in values if v.tag == "AccountCurrency"), None)
            or "EUR"
        )
        rates: dict[str, float] = {base_currency: 1.0}
        # Primary : ExchangeRate tag
        for v in values:
            if v.tag == "ExchangeRate" and v.currency and v.currency != "BASE":
                try:
                    ibkr_rate = float(v.value)
                    if ibkr_rate > 0:
                        rates[v.currency] = 1.0 / ibkr_rate
                except (TypeError, ValueError):
                    pass
        # Fallback : dériver depuis StockMarketValue BASE / StockMarketValue(currency)
        smv_base = _base_value(values, "StockMarketValue")
        if smv_base > 0:
            for v in values:
                if v.tag == "StockMarketValue" and v.currency not in (None, "", "BASE", base_currency):
                    if v.currency in rates:
                        continue  # déjà depuis ExchangeRate
                    try:
                        native = float(v.value)
                        if native > 0:
                            rates[v.currency] = smv_base / native
                    except (TypeError, ValueError):
                        pass
        return rates, base_currency

    def fetch_balances(self) -> list[dict]:
        if not self._ib:
            return []
        out = []
        for acc in self._ib.managedAccounts():
            values = self._ib.accountValues(acc)
            # Dump les tags pertinents pour diagnostic (premier connect)
            relevant = [(v.tag, v.currency, v.value) for v in values if v.tag in (
                "NetLiquidation", "TotalCashValue", "TotalCashBalance",
                "GrossPositionValue", "StockMarketValue", "AccountCurrency",
            )]
            log.info("IBKR: account=%s values_sample=%s", acc, relevant[:20])

            total = _base_value(values, "NetLiquidation")
            cash = _base_value(values, "TotalCashValue")
            if cash == 0:
                cash = _base_value(values, "TotalCashBalance")
            positions_val = _base_value(values, "GrossPositionValue")
            if positions_val == 0:
                positions_val = max(0.0, total - cash)
            currency = (
                next((v.value for v in values if v.tag == "AccountCurrency"), None)
                or "EUR"
            )
            out.append({
                "account_id": acc,
                "accountNumber": acc,          # matching pour portfolio.py (TR-shape)
                "productType": "DEFAULT",
                "label": f"IBKR {acc}",
                "amount": cash,                # portfolio.py somme 'amount' pour cash total
                "cash": cash,
                "total_value": total,
                "positions_value": positions_val,
                "currency": currency,
                "currencyId": currency,
            })
        return out

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str) -> None:
        pass
