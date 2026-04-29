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
