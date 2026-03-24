from src.connectors.base import ConnectorWorker


class IBKRWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._ib = None

    def connect(self, credentials: dict):
        from ib_async import IB

        self._ib = IB()
        host = credentials.get("host", "127.0.0.1")
        port = int(credentials.get("port", 4001))
        try:
            self._ib.connect(host, port, clientId=1)
            self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def disconnect(self):
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._ib = None

    def fetch_accounts(self) -> list[dict]:
        if not self._ib:
            return []
        accounts = self._ib.managedAccounts()
        return [{"id": acc, "name": acc, "type": "margin"} for acc in accounts]

    def fetch_positions(self) -> list[dict]:
        if not self._ib:
            return []
        positions = self._ib.positions()
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
            for p in positions
        ]

    def fetch_balances(self) -> list[dict]:
        if not self._ib:
            return []
        summaries = []
        for acc in self._ib.managedAccounts():
            values = self._ib.accountValues(acc)
            net_liq = next((v.value for v in values if v.tag == "NetLiquidation"), 0)
            cash = next((v.value for v in values if v.tag == "TotalCashBalance"), 0)
            currency = next((v.currency for v in values if v.tag == "NetLiquidation"), "EUR")
            summaries.append({
                "account_id": acc,
                "cash": float(cash),
                "total_value": float(net_liq),
                "positions_value": float(net_liq) - float(cash),
                "currency": currency,
            })
        return summaries

    def fetch_transactions(self) -> list[dict]:
        return []

    def submit_2fa(self, code: str):
        pass
