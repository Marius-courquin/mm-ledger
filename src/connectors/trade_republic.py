import hashlib
import base64
import json
import logging

from src.connectors.base import ConnectorWorker

log = logging.getLogger("tr_worker")


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
            log.info("Getting WAF token via headless Chrome...")
            waf_token = self._get_waf_token()
            log.info(f"WAF token: {'OK' if waf_token else 'EMPTY'} ({len(waf_token)} chars)")

            log.info("Sending login request...")
            process_id = self._login(waf_token)

            if process_id:
                self._pending_process_id = process_id
                log.info(f"2FA required, processId={process_id}")
                self.event_queue.put({
                    "type": "status", "state": "waiting_2fa",
                    "detail": "Enter the code from the Trade Republic app",
                })
            else:
                log.info("Login succeeded without 2FA")
                self.event_queue.put({"type": "status", "state": "connected"})
        except Exception as e:
            log.error(f"Connect failed: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})

    def _get_waf_token(self) -> str:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import time

        options = Options()
        # Use Brave if available (better WAF bypass than vanilla Chromium)
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        import os
        if os.path.exists(brave_path):
            options.binary_location = brave_path
            log.info("Using Brave for WAF bypass")
        else:
            log.info("Brave not found, using default Chrome")
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=400,300")
        options.add_argument("--window-position=9999,9999")
        options.add_argument("--disable-notifications")

        log.info("Launching headless browser...")
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)

        try:
            driver.get("https://app.traderepublic.com/login")
            log.info("Page loaded, waiting for WAF cookie...")

            # Poll for the WAF cookie (up to 15s)
            for i in range(30):
                time.sleep(0.5)
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie["name"] == "aws-waf-token":
                        log.info(f"WAF cookie found after {(i+1)*0.5}s")
                        return cookie["value"]

            # Fallback: JS API
            log.info("No cookie, trying JS fallback...")
            token = driver.execute_script(
                "return window.AwsWafIntegration?.getToken()"
            )
            if token:
                log.info("WAF token from JS API")
                return token

            log.warning("No WAF token found, proceeding without it")
            return ""
        except Exception as e:
            log.error(f"WAF token error: {e}")
            return ""
        finally:
            driver.quit()

    def _login(self, waf_token: str) -> str | None:
        import requests

        device_id = base64.b64encode(
            hashlib.sha512(f"mm-ledger-{self._phone}".encode()).digest()
        ).decode()

        headers = {"Content-Type": "application/json"}
        if waf_token:
            headers["x-aws-waf-token"] = waf_token

        resp = requests.post(
            "https://api.traderepublic.com/api/v1/auth/web/login",
            json={"phoneNumber": self._phone, "pin": self._pin},
            headers=headers,
            timeout=15,
        )
        log.info(f"Login response: {resp.status_code}")
        if resp.status_code != 200:
            log.error(f"Login failed: {resp.text[:200]}")
            raise Exception(f"Login HTTP {resp.status_code}")
        try:
            data = resp.json()
        except Exception:
            log.error(f"Login response not JSON: {resp.text[:200]}")
            raise Exception("Login response was not JSON (likely WAF block)")

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
                timeout=15,
            )
            data = resp.json()
            if "sessionToken" in data:
                self._session_token = data["sessionToken"]
                self.event_queue.put({"type": "status", "state": "connected"})
            else:
                self.event_queue.put({"type": "error", "message": f"2FA failed: {data}"})
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
