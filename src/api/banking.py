"""
Open Banking routes — Enable Banking integration.

Flow:
1. GET  /api/banking/banks?country=FR          → list available banks
2. POST /api/banking/connect {bank, country}    → get redirect URL
3. GET  /api/banking/callback?code=...          → handle bank redirect, create session
4. GET  /api/banking/accounts                   → list connected bank accounts
5. GET  /api/banking/accounts/{uid}/balances    → get balances
6. GET  /api/banking/accounts/{uid}/transactions → get transactions
"""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, Depends
from fastapi.responses import RedirectResponse

from src.api import deps
from src.api.middleware import get_current_user, AuthUser
from src.config import DATA_DIR

router = APIRouter(prefix="/api/banking", tags=["banking"])
log = logging.getLogger("banking")


def _get_client(user_id: str):
    """Get or create Enable Banking client for user."""
    from src.connectors.enable_banking import EnableBankingClient

    # Credentials stored in user's vault
    vault = deps.get_vault(user_id)
    if vault.status != "unlocked":
        raise HTTPException(423, "Coffre-fort verrouillé")

    creds = vault.retrieve("enable_banking")
    if not creds:
        raise HTTPException(404, "Enable Banking non configuré. Ajoutez vos credentials dans les paramètres.")

    app_id = creds.get("application_id", "")
    pem_path = creds.get("pem_path", "")

    if not app_id or not pem_path:
        raise HTTPException(400, "application_id et pem_path requis")

    pem_content = Path(pem_path).read_text() if Path(pem_path).exists() else ""
    if not pem_content:
        raise HTTPException(400, f"Fichier PEM introuvable: {pem_path}")

    return EnableBankingClient(app_id, pem_content)


def _get_sessions_store(user_id: str) -> Path:
    """JSON file storing active banking sessions for a user."""
    path = deps.users_dir / user_id / "banking_sessions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_sessions(user_id: str) -> list[dict]:
    path = _get_sessions_store(user_id)
    if path.exists():
        return json.loads(path.read_text())
    return []


def _save_sessions(user_id: str, sessions: list[dict]):
    path = _get_sessions_store(user_id)
    path.write_text(json.dumps(sessions, indent=2))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/banks")
def list_banks(country: str = "FR", user: AuthUser = Depends(get_current_user)):
    """List available banks for Open Banking connection."""
    client = _get_client(user.id)
    banks = client.list_banks(country)
    # Simplify response for frontend
    return [
        {
            "name": b["name"],
            "country": b["country"],
            "logo": b.get("logo", ""),
        }
        for b in banks
    ]


@router.post("/connect")
def connect_bank(body: dict, request: Request, user: AuthUser = Depends(get_current_user)):
    """Start bank connection. Returns redirect URL."""
    bank_name = body.get("bank_name", "")
    country = body.get("country", "FR")

    if not bank_name:
        raise HTTPException(400, "bank_name requis")

    client = _get_client(user.id)

    # Build redirect URL (back to our app)
    base_url = str(request.base_url).rstrip("/")
    redirect_url = f"{base_url}/api/banking/callback"

    result = client.start_auth(bank_name, country, redirect_url)
    log.info(f"Bank auth started for {bank_name}: {result.get('authorization_id')}")

    return {
        "redirect_url": result["url"],
        "authorization_id": result.get("authorization_id"),
    }


@router.get("/callback")
def bank_callback(code: str = Query(None), error: str = Query(None), user: AuthUser = Depends(get_current_user)):
    """Handle bank redirect after user authenticates."""
    if error:
        raise HTTPException(400, f"Autorisation refusée: {error}")
    if not code:
        raise HTTPException(400, "Code d'autorisation manquant")

    client = _get_client(user.id)
    session = client.create_session(code)

    # Store session
    sessions = _load_sessions(user.id)
    sessions.append({
        "session_id": session["session_id"],
        "bank_name": session.get("aspsp", {}).get("name", ""),
        "accounts": [
            {
                "uid": a["uid"],
                "iban": a.get("account_id", {}).get("iban", ""),
                "name": a.get("name", ""),
                "currency": a.get("currency", "EUR"),
                "type": a.get("cash_account_type", ""),
            }
            for a in session.get("accounts", [])
        ],
        "valid_until": session.get("access", {}).get("valid_until", ""),
    })
    _save_sessions(user.id, sessions)

    log.info(f"Bank connected: {session.get('aspsp', {}).get('name')}, {len(session.get('accounts', []))} accounts")

    # Redirect to frontend
    return RedirectResponse(url="/accounts")


@router.get("/accounts")
def list_banking_accounts(user: AuthUser = Depends(get_current_user)):
    """List all connected Open Banking accounts."""
    sessions = _load_sessions(user.id)
    accounts = []
    for s in sessions:
        for a in s.get("accounts", []):
            accounts.append({
                **a,
                "bank_name": s["bank_name"],
                "session_id": s["session_id"],
                "valid_until": s["valid_until"],
            })
    return accounts


@router.get("/accounts/{account_uid}/balances")
def get_banking_balances(account_uid: str, user: AuthUser = Depends(get_current_user)):
    """Get balances for an Open Banking account."""
    client = _get_client(user.id)
    balances = client.get_balances(account_uid)
    return balances


@router.get("/accounts/{account_uid}/transactions")
def get_banking_transactions(
    account_uid: str,
    date_from: str = Query(None),
    date_to: str = Query(None),
    user: AuthUser = Depends(get_current_user),
):
    """Get transactions for an Open Banking account."""
    client = _get_client(user.id)
    transactions = client.get_transactions(account_uid, date_from, date_to)
    # Normalize to our format
    return [
        {
            "date": t.get("booking_date", ""),
            "label": " ".join(t.get("remittance_information", [])) or t.get("creditor", {}).get("name", "") or t.get("debtor", {}).get("name", ""),
            "amount": float(t.get("transaction_amount", {}).get("amount", 0)),
            "currency": t.get("transaction_amount", {}).get("currency", "EUR"),
            "type": "income" if t.get("credit_debit_indicator") == "CRDT" else "expense",
        }
        for t in transactions
    ]


@router.delete("/sessions/{session_id}")
def disconnect_bank(session_id: str, user: AuthUser = Depends(get_current_user)):
    """Revoke a banking session."""
    client = _get_client(user.id)
    try:
        client.delete_session(session_id)
    except Exception:
        pass
    sessions = _load_sessions(user.id)
    sessions = [s for s in sessions if s["session_id"] != session_id]
    _save_sessions(user.id, sessions)
    return {"status": "disconnected"}
