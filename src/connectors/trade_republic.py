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
                    "detail": f"Entrez le code à 4 chiffres depuis l'app Trade Republic ({countdown}s)",
                    "method": "sms",
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
                # Auto-fetch data after successful connection
                self._auto_fetch()
            else:
                log.error(f"No tr_session in cookies. Headers: {dict(resp.headers)}")
                self.event_queue.put({"type": "error", "message": "2FA OK but no session token in cookies"})
        except Exception as e:
            log.error(f"2FA error: {e}")
            self.event_queue.put({"type": "error", "message": str(e)})

    # Map TR productType to human-readable account labels
    PRODUCT_LABELS = {
        "DEFAULT": "CTO",
        "PEA": "PEA",
        "CRYPTO": "Crypto",
        "PRIVATE_EQUITY": "Private Equity",
    }

    def _auto_fetch(self):
        """Fetch cash + positions + live prices for all accounts."""
        try:
            log.info("Auto-fetching data — opening WS...")
            import websockets.sync.client as ws_client
            with ws_client.connect("wss://api.traderepublic.com", close_timeout=10, open_timeout=10) as ws:
                log.info("WS connected, sending handshake...")
                self._ws_connect(ws)

                # 1. Accounts
                accounts_data = self._ws_sub(ws, {"type": "accountPairs", "token": self._session_token})
                log.info(f"Accounts: {len(accounts_data.get('accounts', []))} found")
                if accounts_data:
                    self.event_queue.put({"type": "accounts", "data": accounts_data})

                accs = accounts_data.get("accounts", []) if isinstance(accounts_data, dict) else []

                # 2. Cash per account
                cash = self._ws_sub(ws, {"type": "availableCash", "token": self._session_token})
                # Map cash to accounts
                cash_list = cash if isinstance(cash, list) else [cash] if cash else []
                for c in cash_list:
                    # Find which account this cash belongs to
                    for acc in accs:
                        if acc.get("cashAccountNumber") == c.get("accountNumber"):
                            c["productType"] = acc.get("productType", "DEFAULT")
                            c["label"] = self.PRODUCT_LABELS.get(acc["productType"], acc["productType"])
                            break
                log.info(f"Cash: {cash_list}")
                self.event_queue.put({"type": "balances", "data": cash_list})

                # 3. Positions per account + live prices
                all_accounts_data = []
                for acc in accs:
                    sec_acc_no = acc.get("securitiesAccountNumber")
                    product_type = acc.get("productType", "DEFAULT")
                    account_label = self.PRODUCT_LABELS.get(product_type, product_type)
                    if not sec_acc_no:
                        continue

                    portfolio = self._ws_sub(ws, {
                        "type": "compactPortfolioByType",
                        "token": self._session_token,
                        "secAccNo": sec_acc_no,
                    })
                    if not portfolio or not isinstance(portfolio, dict):
                        continue

                    # Fetch ticker prices for each position
                    for cat in portfolio.get("categories", []):
                        cat_type = cat.get("categoryType", "")
                        for pos in cat.get("positions", []):
                            isin = pos.get("isin", "")
                            # Crypto uses bare ISIN, stocks use ISIN.LSX
                            # Crypto = bare ISIN, private equity = skip, stocks = ISIN.LSX
                            if cat_type == "privateMarkets":
                                continue  # No ticker available

                            # Build ticker ID: stocks = ISIN.LSX, crypto = try multiple formats
                            if cat_type == "cryptos":
                                # Try: bare ISIN, then shortName-based formats
                                crypto_ids = [isin, f"{isin}.CXTR"]
                                ticker = None
                                for tid in crypto_ids:
                                    try:
                                        ticker = self._ws_sub(ws, {
                                            "type": "ticker",
                                            "token": self._session_token,
                                            "id": tid,
                                        })
                                        if ticker and not ticker.get("errors"):
                                            log.info(f"Crypto ticker {tid}: OK")
                                            break
                                        ticker = None
                                    except Exception:
                                        continue
                            else:
                                ticker_id = f"{isin}.LSX"
                                ticker = self._ws_sub(ws, {
                                    "type": "ticker",
                                    "token": self._session_token,
                                    "id": ticker_id,
                                })

                            try:
                                log.info(f"Ticker {isin}: {json.dumps(ticker)[:150] if ticker else 'None'}")
                                if ticker and isinstance(ticker, dict):
                                    price = (ticker.get("last", {}).get("price")
                                             or ticker.get("bid", {}).get("price")
                                             or ticker.get("ask", {}).get("price"))
                                    if price:
                                        pos["currentPrice"] = float(price)
                                        log.info(f"  -> price={price}")
                            except Exception as e:
                                log.warning(f"Ticker {ticker_id} failed: {e}")

                            # Tag position with account info
                            pos["accountId"] = sec_acc_no
                            pos["accountLabel"] = account_label
                            pos["productType"] = product_type

                    all_accounts_data.append({
                        "secAccNo": sec_acc_no,
                        "productType": product_type,
                        "label": account_label,
                        **portfolio,
                    })
                    log.info(f"Portfolio {account_label} ({sec_acc_no}): {sum(len(c.get('positions', [])) for c in portfolio.get('categories', []))} positions")

                self.event_queue.put({"type": "positions", "data": all_accounts_data})
                total_positions = sum(
                    len(pos)
                    for a in all_accounts_data
                    for c in a.get("categories", [])
                    for pos in [c.get("positions", [])]
                )
                log.info(f"Auto-fetch done: {len(all_accounts_data)} accounts, {total_positions} positions with prices")

                # After positions, fetch transactions
                try:
                    all_txs = []
                    after = None
                    while True:
                        payload = {"type": "timelineTransactions", "token": self._session_token}
                        if after:
                            payload["after"] = after
                        data = self._ws_sub(ws, payload)
                        if not data or not data.get("items"):
                            break
                        all_txs.extend(data["items"])
                        after = data.get("cursors", {}).get("after")
                        if not after:
                            break
                    if all_txs:
                        # Normalize TR transactions to our format
                        normalized = []
                        for tx in all_txs:
                            amount_data = tx.get("amount", {})
                            amount = float(amount_data.get("value", 0)) if isinstance(amount_data, dict) else 0
                            normalized.append({
                                "date": tx.get("timestamp", ""),
                                "label": tx.get("title", ""),
                                "amount": amount,
                                "type": "income" if amount > 0 else "expense",
                                "raw_type": tx.get("eventType", ""),
                            })
                        self.event_queue.put({"type": "transactions", "data": normalized})
                        log.info(f"Fetched {len(normalized)} transactions")
                except Exception as e:
                    log.warning(f"Transaction fetch failed: {e}")

        except Exception as e:
            log.error(f"Auto-fetch error: {e}")

    def fetch_accounts(self) -> list[dict]:
        return self._ws_one_shot("accountPairs")

    def fetch_positions(self) -> list[dict]:
        return self._ws_one_shot("compactPortfolioByType")

    def fetch_balances(self) -> list[dict]:
        return self._ws_one_shot("availableCash")

    def fetch_transactions(self) -> list[dict]:
        """Fetch all transactions with pagination (like the scraper)."""
        import websockets.sync.client as ws_client
        all_items = []
        with ws_client.connect("wss://api.traderepublic.com") as ws:
            self._ws_connect(ws)
            after = None
            while True:
                payload = {"type": "timelineTransactions", "token": self._session_token}
                if after:
                    payload["after"] = after
                data = self._ws_sub(ws, payload)
                if not data or not data.get("items"):
                    break
                all_items.extend(data["items"])
                after = data.get("cursors", {}).get("after")
                if not after:
                    break
                log.info(f"Fetched {len(all_items)} transactions so far...")
        return all_items

    # --- WebSocket helpers (exact protocol from trade_republic_scraper) ---

    _ws_msg_id = 0

    def _ws_connect(self, ws):
        """Send the connect handshake."""
        locale = {
            "locale": "fr",
            "platformId": "webtrading",
            "platformVersion": "safari - 18.3.0",
            "clientId": "app.traderepublic.com",
            "clientVersion": "3.151.3",
        }
        ws.send(f"connect 31 {json.dumps(locale)}")
        ack = ws.recv(timeout=10)
        log.info(f"WS connect ack: {ack[:100]}")

    def _ws_sub(self, ws, payload: dict):
        """Subscribe, receive one response, unsubscribe. Returns parsed data."""
        self._ws_msg_id += 1
        mid = self._ws_msg_id
        ws.send(f"sub {mid} {json.dumps(payload)}")
        raw = ws.recv(timeout=15)
        ws.send(f"unsub {mid}")
        # Don't wait for unsub ack — TR doesn't always send one and it adds 5s per call
        return self._parse_ws_response(raw)

    def _parse_ws_response(self, raw: str):
        """Parse WS response: find JSON object or array in the raw string."""
        # Try object first
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
        # Try array
        start = raw.find("[")
        end = raw.rfind("]")
        if start != -1 and end != -1 and end > start:
            return json.loads(raw[start:end + 1])
        log.warning(f"WS response not JSON: {raw[:100]}")
        return None

    def _ws_one_shot(self, sub_type: str) -> list[dict]:
        """Open WS, connect, subscribe once, close."""
        import websockets.sync.client as ws_client
        with ws_client.connect("wss://api.traderepublic.com", close_timeout=10, open_timeout=10) as ws:
            self._ws_connect(ws)
            data = self._ws_sub(ws, {"type": sub_type, "token": self._session_token})
            return data if data else []
