from datetime import datetime, timezone
from decimal import Decimal

from src.api import deps
from src.auth import decode_jwt


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def test_create_loan(client):
    _setup(client)
    r = client.post("/api/loans", json={
        "name": "Crédit immo Paris", "loan_type": "immo",
        "initial_capital": 250000, "monthly_payment": 1200,
        "total_months": 240, "start_date": "2020-01-01"
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "Crédit immo Paris"
    assert body["months_remaining"] >= 0
    assert body["end_date"] == "2040-01-01"


def test_list_loans(client):
    _setup(client)
    for n in ("A", "B"):
        client.post("/api/loans", json={
            "name": n, "loan_type": "conso", "initial_capital": 5000,
            "monthly_payment": 150, "total_months": 36, "start_date": "2024-06-01"
        })
    r = client.get("/api/loans")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_get_loan_404(client):
    _setup(client)
    r = client.get("/api/loans/999")
    assert r.status_code == 404


def test_update_loan(client):
    _setup(client)
    cr = client.post("/api/loans", json={
        "name": "L1", "loan_type": "auto", "initial_capital": 12000,
        "monthly_payment": 200, "total_months": 60, "start_date": "2024-01-01"
    })
    lid = cr.json()["id"]
    r = client.put(f"/api/loans/{lid}", json={"monthly_payment": 250, "name": "L1 renamed"})
    assert r.status_code == 200
    assert r.json()["monthly_payment"] == 250
    assert r.json()["name"] == "L1 renamed"


def test_delete_loan(client):
    _setup(client)
    cr = client.post("/api/loans", json={
        "name": "L1", "loan_type": "other", "initial_capital": 1000,
        "monthly_payment": 100, "total_months": 12, "start_date": "2024-01-01"
    })
    lid = cr.json()["id"]
    r = client.delete(f"/api/loans/{lid}")
    assert r.status_code == 204
    r = client.get(f"/api/loans/{lid}")
    assert r.status_code == 404


def test_summary(client):
    _setup(client)
    client.post("/api/loans", json={
        "name": "Immo", "loan_type": "immo", "initial_capital": 200000,
        "monthly_payment": 1000, "total_months": 240, "start_date": "2024-01-01"
    })
    client.post("/api/loans", json={
        "name": "Auto", "loan_type": "auto", "initial_capital": 12000,
        "monthly_payment": 200, "total_months": 60, "start_date": "2024-01-01"
    })
    # Prêt terminé : ne doit pas compter dans summary
    client.post("/api/loans", json={
        "name": "Old", "loan_type": "conso", "initial_capital": 1000,
        "monthly_payment": 100, "total_months": 6, "start_date": "2010-01-01"
    })
    r = client.get("/api/loans/summary")
    assert r.status_code == 200
    body = r.json()
    assert body["active_count"] == 2
    assert body["total_monthly_payment"] == 1200.0
    assert body["last_end_date"] is not None


def test_unauth(client):
    r = client.get("/api/loans")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# Helpers pour les tests candidates / link / ignore
# ---------------------------------------------------------------------------

def _setup_liability_in_live_data(
    user_id: str,
    account_id: str = "woob:bp:abc999",
    label: str = "Vcc - Pret Jeune",
    balance: float = -4000.0,
):
    """Injecte un compte liability + balance dans manager.live_data."""
    from src.normalizers.types import CanonicalAccount, CanonicalBalance

    deps.manager.live_data[f"{user_id}:woob-1"] = {
        "accounts": [CanonicalAccount(
            id=account_id,
            connector_id=f"{user_id}:woob-1",
            connector_type="woob_bank",
            label=label,
            kind="liability",
        )],
        "balances": [CanonicalBalance(
            account_id=account_id,
            total_value=Decimal(str(balance)),
            cash=Decimal(str(balance)),
            as_of=datetime.now(timezone.utc),
        )],
        "positions": [],
        "transactions": [],
    }


def test_candidates_returns_unlinked_liability_accounts(client):
    """GET /api/loans/candidates retourne les comptes liability non liés non ignorés."""
    user_id = _setup(client)
    _setup_liability_in_live_data(user_id)
    resp = client.get("/api/loans/candidates")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["account_id"] == "woob:bp:abc999"
    assert data[0]["balance"] == -4000.0
    assert data[0]["connector_type"] == "woob_bank"


def test_candidates_excludes_linked_accounts(client):
    """Un compte lié à un loan ne doit plus apparaître dans candidates."""
    user_id = _setup(client)
    _setup_liability_in_live_data(user_id)
    # Crée un loan
    resp = client.post("/api/loans", json={
        "name": "Prêt Jeune", "loan_type": "conso",
        "initial_capital": 4000, "monthly_payment": 200,
        "total_months": 20, "start_date": "2026-01-01",
    })
    loan_id = resp.json()["id"]
    # Lien
    resp = client.post(f"/api/loans/{loan_id}/link",
                       json={"account_id": "woob:bp:abc999"})
    assert resp.status_code == 200
    # Le candidat ne doit plus apparaître
    resp = client.get("/api/loans/candidates")
    assert resp.json() == []


def test_candidates_excludes_ignored_accounts(client):
    user_id = _setup(client)
    _setup_liability_in_live_data(user_id)
    resp = client.post("/api/loans/candidates/woob:bp:abc999/ignore")
    assert resp.status_code == 204
    resp = client.get("/api/loans/candidates")
    assert resp.json() == []


def test_unignore_candidate_restores_visibility(client):
    user_id = _setup(client)
    _setup_liability_in_live_data(user_id)
    client.post("/api/loans/candidates/woob:bp:abc999/ignore")
    resp = client.delete("/api/loans/candidates/woob:bp:abc999/ignore")
    assert resp.status_code == 204
    resp = client.get("/api/loans/candidates")
    assert len(resp.json()) == 1


def test_from_account_creates_loan_and_link(client):
    """POST /api/loans/from-account crée un loan + le lien atomiquement, le candidat disparaît."""
    user_id = _setup(client)
    _setup_liability_in_live_data(user_id)

    resp = client.post("/api/loans/from-account", json={
        "account_id": "woob:bp:abc999",
        "name": "Prêt depuis banque",
        "loan_type": "conso",
        "initial_capital": 4000,
        "monthly_payment": 200,
        "total_months": 20,
        "start_date": "2026-01-01",
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Prêt depuis banque"
    assert body["initial_capital"] == 4000

    # Le candidat ne doit plus apparaître
    candidates = client.get("/api/loans/candidates").json()
    assert all(c["account_id"] != "woob:bp:abc999" for c in candidates)
