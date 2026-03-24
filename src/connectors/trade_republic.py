import hashlib
import base64
import json
import logging
import os
import sys

from src.connectors.base import ConnectorWorker

# Configure logging in subprocess
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", stream=sys.stderr)
log = logging.getLogger("tr_worker")


class TradeRepublicWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._session_token = None
        self._phone = None
        self._pin = None
        self._pending_process_id = None
        self._waf_token = None
        self._waf_cookies = {}

    def connect(self, credentials: dict):
        self._phone = credentials["phone"]
        self._pin = credentials["pin"]
        self.event_queue.put({"type": "status", "state": "connecting"})

        try:
            log.info("Starting login via browser (WAF bypass)...")
            self._waf_token, self._waf_cookies = self._browser_login()
            result = self._api_login(self._waf_token, self._waf_cookies)

            if result.get("processId"):
                self._pending_process_id = result["processId"]
                log.info(f"2FA required, processId={result['processId']}")
                self.event_queue.put({
                    "type": "status", "state": "waiting_2fa",
                    "detail": "Enter the code from the Trade Republic app",
                })
            elif result.get("sessionToken"):
                self._session_token = result["sessionToken"]
                log.info("Login succeeded without 2FA")
                self.event_queue.put({"type": "status", "state": "connected"})
            else:
                raise Exception(f"Unexpected login result: {result}")
        except Exception as e:
            log.error(f"Connect failed: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})

    def _browser_login(self) -> dict:
        """Login via browser — the login API call is made FROM the browser
        so the WAF token is automatically included in the request context."""
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        import time

        options = Options()
        brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        if os.path.exists(brave_path):
            options.binary_location = brave_path
            log.info("Using Brave")
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=400,300")
        options.add_argument("--window-position=9999,9999")
        options.add_argument("--disable-notifications")

        log.info("Launching browser...")
        driver = webdriver.Chrome(options=options)

        # Anti-detection: hide webdriver flag
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })

        driver.set_page_load_timeout(30)

        try:
            # Load TR login page to trigger WAF challenge
            driver.get("https://app.traderepublic.com/login")
            log.info("Page loaded, waiting for WAF...")

            # Wait for WAF cookie
            waf_token = None
            for i in range(40):  # 20 seconds max
                time.sleep(0.5)
                cookies = driver.get_cookies()
                for cookie in cookies:
                    if cookie["name"] == "aws-waf-token":
                        waf_token = cookie["value"]
                        log.info(f"WAF cookie found after {(i+1)*0.5}s")
                        break
                if waf_token:
                    break

            if not waf_token:
                waf_token = driver.execute_script(
                    "return window.AwsWafIntegration?.getToken()"
                ) or ""
                log.info(f"WAF from JS: {'OK' if waf_token else 'EMPTY'}")

            # Collect ALL cookies from the browser session
            all_cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
            log.info(f"Cookies: {list(all_cookies.keys())}")

            return waf_token, all_cookies

        finally:
            driver.quit()

    def _api_login(self, waf_token: str, cookies: dict) -> dict:
        """Login via Python requests, passing the WAF token + browser cookies."""
        import requests

        session = requests.Session()
        for name, value in cookies.items():
            session.cookies.set(name, value, domain=".traderepublic.com")

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        }
        if waf_token:
            headers["x-aws-waf-token"] = waf_token

        log.info("Sending login request...")
        resp = session.post(
            "https://api.traderepublic.com/api/v1/auth/web/login",
            json={"phoneNumber": self._phone, "pin": self._pin},
            headers=headers,
            timeout=15,
        )
        log.info(f"Login response: {resp.status_code}")

        if resp.status_code != 200:
            log.error(f"Login body: {resp.text[:300]}")
            raise Exception(f"Login HTTP {resp.status_code}")

        return resp.json()

    def disconnect(self):
        self._session_token = None

    def submit_2fa(self, code: str):
        import requests
        try:
            session = requests.Session()
            for name, value in self._waf_cookies.items():
                session.cookies.set(name, value, domain=".traderepublic.com")

            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            }
            if self._waf_token:
                headers["x-aws-waf-token"] = self._waf_token

            url = f"https://api.traderepublic.com/api/v1/auth/web/login/{self._pending_process_id}/{code}"
            log.info(f"Submitting 2FA code to {url}")
            resp = session.post(url, headers=headers, timeout=15)
            log.info(f"2FA response: {resp.status_code}, body: {resp.text[:200]}")

            if resp.status_code != 200:
                self.event_queue.put({"type": "error", "message": f"2FA HTTP {resp.status_code}"})
                return

            data = resp.json()
            if "sessionToken" in data:
                self._session_token = data["sessionToken"]
                log.info("2FA success, connected")
                self.event_queue.put({"type": "status", "state": "connected"})
            else:
                log.error(f"2FA unexpected response: {data}")
                self.event_queue.put({"type": "error", "message": f"2FA failed: {data}"})
        except Exception as e:
            log.error(f"2FA error: {e}")
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
