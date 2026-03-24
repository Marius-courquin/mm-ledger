import hashlib
import uuid
import base64
import json
import logging
import os
import sys

from src.connectors.base import ConnectorWorker

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", stream=sys.stderr)
log = logging.getLogger("tr_worker")

TR_HEADERS_BASE = {
    "Accept": "*/*",
    "Accept-Language": "fr",
    "Cache-Control": "no-cache",
    "Content-Type": "application/json",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "x-tr-app-version": "13.40.5",
    "x-tr-platform": "web",
}


def _generate_device_info() -> str:
    device_id = hashlib.sha512(uuid.uuid4().bytes).hexdigest()
    return base64.b64encode(json.dumps({"stableDeviceId": device_id}).encode()).decode()


class TradeRepublicWorker(ConnectorWorker):
    def __init__(self, cmd_queue, event_queue, config):
        super().__init__(cmd_queue, event_queue, config)
        self._session_token = None
        self._phone = None
        self._pin = None
        self._pending_process_id = None
        self._headers = {}

    def connect(self, credentials: dict):
        self._phone = credentials["phone"]
        self._pin = credentials["pin"]
        self.event_queue.put({"type": "status", "state": "connecting"})

        try:
            # Step 1: WAF bypass
            log.info("Getting WAF token via Brave...")
            waf_token = self._get_waf_token()

            # Step 2: Build headers
            self._headers = {
                **TR_HEADERS_BASE,
                "x-aws-waf-token": waf_token or "",
                "x-tr-device-info": _generate_device_info(),
            }

            # Step 3: Login
            log.info("Sending login request...")
            result = self._login()

            if result.get("processId"):
                self._pending_process_id = result["processId"]
                countdown = result.get("countdownInSeconds", 60)
                log.info(f"2FA required, processId={result['processId']}, countdown={countdown}s")
                self.event_queue.put({
                    "type": "status", "state": "waiting_2fa",
                    "detail": f"Enter the 4-digit code from Trade Republic app ({countdown}s)",
                })
            else:
                log.warning(f"Unexpected login response: {result}")
                self.event_queue.put({"type": "error", "message": f"Unexpected: {result}"})
        except Exception as e:
            log.error(f"Connect failed: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})

    def _get_waf_token(self) -> str:
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

        driver = webdriver.Chrome(options=options)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        })
        driver.set_page_load_timeout(30)

        try:
            driver.get("https://app.traderepublic.com/")
            log.info("Page loaded, polling for WAF cookie...")

            for i in range(40):
                time.sleep(0.5)
                for cookie in driver.get_cookies():
                    if "aws-waf-token" in cookie.get("name", ""):
                        log.info(f"WAF cookie found after {(i+1)*0.5}s")
                        return cookie["value"]

            # JS fallback
            token = driver.execute_script(
                "return window.AWSWafIntegration && window.AWSWafIntegration.getToken();"
            ) or ""
            log.info(f"WAF JS fallback: {'OK' if token else 'EMPTY'}")
            return token
        except Exception as e:
            log.error(f"WAF error: {e}")
            return ""
        finally:
            driver.quit()

    def _login(self) -> dict:
        import requests
        resp = requests.post(
            "https://api.traderepublic.com/api/v1/auth/web/login",
            json={"phoneNumber": self._phone, "pin": self._pin},
            headers=self._headers,
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
            # 2FA verify: code is in the URL path, no JSON body
            url = f"https://api.traderepublic.com/api/v1/auth/web/login/{self._pending_process_id}/{code}"
            log.info(f"Submitting 2FA to {url}")
            resp = requests.post(url, headers=self._headers, timeout=15)
            log.info(f"2FA response: {resp.status_code}")

            if resp.status_code != 200:
                self.event_queue.put({"type": "error", "message": f"2FA HTTP {resp.status_code}"})
                return

            # Session token is in Set-Cookie header, NOT in the body
            session_token = None
            set_cookie = resp.headers.get("Set-Cookie", "")
            log.info(f"Set-Cookie: {set_cookie[:200]}")
            for part in set_cookie.split(","):
                for segment in part.split(";"):
                    segment = segment.strip()
                    if segment.startswith("tr_session="):
                        session_token = segment.split("=", 1)[1]
                        break

            if session_token:
                self._session_token = session_token
                log.info("2FA success — session token obtained")
                self.event_queue.put({"type": "status", "state": "connected"})
            else:
                log.error(f"No tr_session in cookies. Headers: {dict(resp.headers)}")
                self.event_queue.put({"type": "error", "message": "2FA OK but no session token in cookies"})
        except Exception as e:
            log.error(f"2FA error: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})

    def fetch_accounts(self) -> list[dict]:
        return self._ws_request("accountPairs")

    def fetch_positions(self) -> list[dict]:
        return self._ws_request("compactPortfolioByType")

    def fetch_balances(self) -> list[dict]:
        return self._ws_request("availableCash")

    def fetch_transactions(self) -> list[dict]:
        return self._ws_request("timelineTransactions")

    def _ws_request(self, sub_type: str, extra: dict | None = None) -> list[dict]:
        """Send a subscription over the TR WebSocket protocol."""
        import websockets.sync.client as ws_client

        with ws_client.connect("wss://api.traderepublic.com") as ws:
            # Connect handshake
            locale = {
                "locale": "fr",
                "platformId": "webtrading",
                "platformVersion": "safari - 18.3.0",
                "clientId": "app.traderepublic.com",
                "clientVersion": "3.151.3",
            }
            ws.send(f"connect 31 {json.dumps(locale)}")
            ws.recv()  # ack

            # Subscribe
            payload = {"type": sub_type, "token": self._session_token}
            if extra:
                payload.update(extra)
            ws.send(f"sub 1 {json.dumps(payload)}")
            raw = ws.recv()

            # Unsub
            ws.send("unsub 1")

            # Parse: response is like "1 A {json...}"
            # Find first { and parse from there
            idx = raw.find("{")
            if idx == -1:
                idx = raw.find("[")
            if idx >= 0:
                return json.loads(raw[idx:])
            log.warning(f"WS response not JSON: {raw[:100]}")
            return []
