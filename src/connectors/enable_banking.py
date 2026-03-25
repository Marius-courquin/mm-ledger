"""
Enable Banking connector — Open Banking PSD2 via enablebanking.com

Connects to any European bank (BP, Bourso, CE, CA, BNP, etc.) via a single API.
No bank credentials stored — user authenticates directly on their bank's website.

Setup:
1. Create account on enablebanking.com
2. Create application → get application_id + .pem private key
3. Store application_id in connector credentials, .pem in data/enable_banking.pem
"""

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", stream=sys.stderr)
log = logging.getLogger("enable_banking")

API_BASE = "https://api.enablebanking.com"


class EnableBankingClient:
    """REST client for Enable Banking API."""

    def __init__(self, application_id: str, private_key_pem: str):
        self._app_id = application_id
        self._private_key = private_key_pem

    def _get_token(self) -> str:
        """Sign a JWT for API authentication."""
        import jwt as pyjwt

        now = int(datetime.now(timezone.utc).timestamp())
        payload = {
            "iss": "enablebanking.com",
            "aud": "api.enablebanking.com",
            "iat": now,
            "exp": now + 3600,
        }
        return pyjwt.encode(
            payload,
            self._private_key,
            algorithm="RS256",
            headers={"kid": self._app_id},
        )

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        import requests
        r = requests.get(f"{API_BASE}{path}", headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict) -> dict:
        import requests
        r = requests.post(f"{API_BASE}{path}", headers=self._headers(), json=body, timeout=30)
        r.raise_for_status()
        return r.json()

    def _delete(self, path: str):
        import requests
        r = requests.delete(f"{API_BASE}{path}", headers=self._headers(), timeout=30)
        r.raise_for_status()

    # ── Public API ────────────────────────────────────────────────────────────

    def list_banks(self, country: str = "FR") -> list[dict]:
        """List available banks for a country."""
        data = self._get("/aspsps", {"country": country, "psu_type": "personal"})
        return data.get("aspsps", [])

    def start_auth(self, bank_name: str, country: str, redirect_url: str, valid_days: int = 90) -> dict:
        """Start bank authorization. Returns {url, authorization_id}."""
        from datetime import timedelta
        valid_until = (datetime.now(timezone.utc) + timedelta(days=valid_days)).isoformat()
        body = {
            "access": {"valid_until": valid_until},
            "aspsp": {"name": bank_name, "country": country},
            "state": f"mm-ledger-{int(time.time())}",
            "redirect_url": redirect_url,
            "psu_type": "personal",
        }
        return self._post("/auth", body)

    def create_session(self, auth_code: str) -> dict:
        """Exchange auth code for session. Returns {session_id, accounts}."""
        return self._post("/sessions", {"code": auth_code})

    def get_session(self, session_id: str) -> dict:
        """Get session status and accounts."""
        return self._get(f"/sessions/{session_id}")

    def get_balances(self, account_uid: str) -> list[dict]:
        """Get account balances."""
        data = self._get(f"/accounts/{account_uid}/balances")
        return data.get("balances", [])

    def get_transactions(self, account_uid: str, date_from: str | None = None, date_to: str | None = None) -> list[dict]:
        """Get account transactions with pagination."""
        params = {}
        if date_from:
            params["date_from"] = date_from
        if date_to:
            params["date_to"] = date_to

        all_txs = []
        continuation_key = None
        while True:
            if continuation_key:
                params["continuation_key"] = continuation_key
            data = self._get(f"/accounts/{account_uid}/transactions", params)
            all_txs.extend(data.get("transactions", []))
            continuation_key = data.get("continuation_key")
            if not continuation_key:
                break
        return all_txs

    def delete_session(self, session_id: str):
        """Revoke a session."""
        self._delete(f"/sessions/{session_id}")
