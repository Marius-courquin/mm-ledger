from sqlalchemy import insert
from src.api import deps
from src.auth import decode_jwt
from src.db.models import loans


def _setup(client):
    r = client.post("/api/auth/setup", json={"username": "admin", "password": "testpass123"})
    assert r.status_code == 201
    client.post("/api/vault/setup", json={"password": "test"})
    token = r.cookies.get("mm_session")
    return decode_jwt(token, deps.jwt_secret)["user_id"]


def test_get_empty_budget(client):
    _setup(client)
    r = client.get("/api/budget")
    assert r.status_code == 200
    body = r.json()
    assert body["sections"] == []
    assert body["totals"]["investment_capacity"] == 0


def test_crud_section_and_item(client):
    _setup(client)
    rs = client.post("/api/budget/sections", json={"name": "Salaires", "section_type": "income"})
    assert rs.status_code == 201
    sid = rs.json()["id"]
    ri = client.post(f"/api/budget/sections/{sid}/items", json={"label": "Salaire", "amount": 3500})
    assert ri.status_code == 201
    iid = ri.json()["id"]
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 3500
    # Update item
    client.put(f"/api/budget/items/{iid}", json={"amount": 4000})
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 4000
    # Delete item
    client.delete(f"/api/budget/items/{iid}")
    g = client.get("/api/budget").json()
    assert g["totals"]["income"] == 0
    # Update section
    client.put(f"/api/budget/sections/{sid}", json={"name": "Salaires renommé"})
    g = client.get("/api/budget").json()
    assert g["sections"][0]["name"] == "Salaires renommé"
    # Delete section (cascade items)
    client.delete(f"/api/budget/sections/{sid}")
    g = client.get("/api/budget").json()
    assert g["sections"] == []


def test_virtual_section_appears(client):
    user_id = _setup(client)
    engine = deps.get_ledger(user_id)
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=12000,
            monthly_payment=300, total_months=36, start_date="2025-01-01",
        ))
    g = client.get("/api/budget").json()
    virtuals = [s for s in g["sections"] if s["is_virtual"]]
    assert len(virtuals) == 1
    assert virtuals[0]["name"] == "Prêts"
    assert g["totals"]["fixed_expense"] == 300


def test_cant_edit_virtual_section(client):
    _setup(client)
    r = client.put("/api/budget/sections/virtual:loans", json={"name": "X"})
    assert r.status_code == 400
    r = client.delete("/api/budget/sections/virtual:loans")
    assert r.status_code == 400
    r = client.post("/api/budget/sections/virtual:loans/items", json={"label": "X", "amount": 1})
    assert r.status_code == 400
    r = client.put("/api/budget/items/virtual:loan:1", json={"amount": 100})
    assert r.status_code == 400
    r = client.delete("/api/budget/items/virtual:loan:1")
    assert r.status_code == 400


def test_apply_to_projection(client):
    _setup(client)
    rs = client.post("/api/budget/sections", json={"name": "Salaires", "section_type": "income"})
    sid = rs.json()["id"]
    client.post(f"/api/budget/sections/{sid}/items", json={"label": "Salaire", "amount": 1000})
    r = client.post("/api/budget/apply-to-projection", json={"cash_share": 0.3, "market_share": 0.7})
    assert r.status_code == 200
    body = r.json()
    assert body["cash_monthly_contribution"] == 300
    assert body["market_monthly_contribution"] == 700
    # Vérifie que projection_settings a bien été MAJ
    s = client.get("/api/projection/settings").json()
    assert s["settings"]["cash_monthly_contribution"] == 300
    assert s["settings"]["market_monthly_contribution"] == 700


def test_apply_to_projection_invalid_shares(client):
    _setup(client)
    r = client.post("/api/budget/apply-to-projection", json={"cash_share": 0.5, "market_share": 0.6})
    assert r.status_code == 400


def test_unauth(client):
    r = client.get("/api/budget")
    assert r.status_code == 401
