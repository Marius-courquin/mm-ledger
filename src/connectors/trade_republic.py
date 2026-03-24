import hashlib
import base64
import json

from src.connectors.base import ConnectorWorker


class TradeRepublicWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._session_token = None
        self._phone = None
        self._pin = None
        self._pending_process_id = None

    def connect(self, credentials: dict):
        self._phone = credentials["phone"]
        self._pin = credentials["pin"]
        self.event_queue.put({"type": "status", "state": "connecting"})

        try:
            waf_token = self._get_waf_token()
            process_id = self._login(waf_token)
            if process_id:
                self._pending_process_id = process_id
                self.event_queue.put({
                    "type": "status", "state": "waiting_2fa",
                    "detail": "Enter the code from the Trade Republic app",
                })
            else:
                self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def _get_waf_token(self) -> str:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import time

        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get("https://app.traderepublic.com/login")
            time.sleep(5)
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie["name"] == "aws-waf-token":
                    return cookie["value"]
            token = driver.execute_script(
                "return window.AwsWafIntegration?.getToken()"
            )
            return token or ""
        finally:
            driver.quit()

    def _login(self, waf_token: str) -> str | None:
        import requests
        device_id = base64.b64encode(
            hashlib.sha512(f"mm-ledger-{self._phone}".encode()).digest()
        ).decode()
        headers = {
            "x-aws-waf-token": waf_token,
            "Content-Type": "application/json",
        }
        resp = requests.post(
            "https://api.traderepublic.com/api/v1/auth/web/login",
            json={"phoneNumber": self._phone, "pin": self._pin},
            headers=headers,
        )
        data = resp.json()
        if "processId" in data:
            return data["processId"]
        if "sessionToken" in data:
            self._session_token = data["sessionToken"]
            return None
        raise Exception(f"Unexpected login response: {data}")

    def disconnect(self):
        self._session_token = None

    def submit_2fa(self, code: str):
        import requests
        try:
            resp = requests.post(
                f"https://api.traderepublic.com/api/v1/auth/web/login/{self._pending_process_id}/{code}",
            )
            data = resp.json()
            self._session_token = data.get("sessionToken")
            self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            self.event_queue.put({"type": "error", "message": str(e)})

    def fetch_accounts(self) -> list[dict]:
        return self._ws_subscribe("accountPairs")

    def fetch_positions(self) -> list[dict]:
        return self._ws_subscribe("compactPortfolioByType")

    def fetch_balances(self) -> list[dict]:
        return self._ws_subscribe("cash")

    def fetch_transactions(self) -> list[dict]:
        return self._ws_subscribe("transactions")

    def _ws_subscribe(self, subscription: str) -> list[dict]:
        import websockets.sync.client as ws_client
        with ws_client.connect("wss://api.traderepublic.com") as ws:
            ws.send(json.dumps({
                "action": "subscribe",
                "token": self._session_token,
                "type": subscription,
            }))
            response = ws.recv()
            return json.loads(response) if isinstance(response, str) else []
