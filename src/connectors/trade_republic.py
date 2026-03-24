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

    def connect(self, credentials: dict):
        self._phone = credentials["phone"]
        self._pin = credentials["pin"]
        self.event_queue.put({"type": "status", "state": "connecting"})

        try:
            log.info("Starting login via browser (WAF bypass)...")
            result = self._browser_login()

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
                # Try JS API fallback
                waf_token = driver.execute_script(
                    "return window.AwsWafIntegration?.getToken()"
                ) or ""
                log.info(f"WAF from JS: {'OK' if waf_token else 'EMPTY'}")

            # Make the login call FROM the browser context
            log.info("Sending login request from browser...")
            result = driver.execute_script("""
                const [phone, pin, wafToken] = arguments;
                const resp = await fetch("https://api.traderepublic.com/api/v1/auth/web/login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        ...(wafToken ? {"x-aws-waf-token": wafToken} : {})
                    },
                    body: JSON.stringify({phoneNumber: phone, pin: pin})
                });
                const text = await resp.text();
                return {status: resp.status, body: text};
            """, self._phone, self._pin, waf_token)

            log.info(f"Login response: {result['status']}")

            if result["status"] != 200:
                raise Exception(f"Login HTTP {result['status']}: {result['body'][:200]}")

            data = json.loads(result["body"])
            return data

        finally:
            driver.quit()

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
                log.info("2FA success, connected")
                self.event_queue.put({"type": "status", "state": "connected"})
            else:
                log.error(f"2FA failed: {data}")
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
