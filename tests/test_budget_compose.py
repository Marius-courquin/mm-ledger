from datetime import date
from sqlalchemy import insert
from src.db.engine import create_engine_and_tables
from src.db.models import budget_sections, budget_items, loans
from src.services.budget_compose import compose_budget


def test_empty_budget(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    view = compose_budget(engine, today=date(2026, 4, 29))
    # Aucun prêt → pas de section virtuelle
    assert view["sections"] == []
    assert view["totals"]["investment_capacity"] == 0


def test_basic_user_sections(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        sec = conn.execute(insert(budget_sections).values(
            name="Salaires", section_type="income", position=0
        ))
        sid_income = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_income, label="Salaire", amount=3500, position=0
        ))
        sec = conn.execute(insert(budget_sections).values(
            name="Logement", section_type="fixed_expense", position=0
        ))
        sid_fixed = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_fixed, label="Loyer", amount=1000, position=0
        ))
        sec = conn.execute(insert(budget_sections).values(
            name="Alimentation", section_type="variable_expense", position=0
        ))
        sid_var = sec.inserted_primary_key[0]
        conn.execute(insert(budget_items).values(
            section_id=sid_var, label="Courses", amount=400, position=0
        ))
    view = compose_budget(engine, today=date(2026, 4, 29))
    totals = view["totals"]
    assert totals["income"] == 3500
    assert totals["fixed_expense"] == 1000
    assert totals["variable_expense"] == 400
    assert totals["expense"] == 1400
    assert totals["investment_capacity"] == 2100


def test_virtual_loan_section(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        conn.execute(insert(loans).values(
            name="Auto", loan_type="auto", initial_capital=12000,
            monthly_payment=300, total_months=36, start_date="2025-01-01",
        ))
        conn.execute(insert(loans).values(
            name="Old", loan_type="conso", initial_capital=1000,
            monthly_payment=100, total_months=6, start_date="2010-01-01",
        ))  # terminé → ne doit pas apparaître
    view = compose_budget(engine, today=date(2026, 4, 29))
    virtuals = [s for s in view["sections"] if s["is_virtual"]]
    assert len(virtuals) == 1
    assert virtuals[0]["name"] == "Prêts"
    assert virtuals[0]["section_type"] == "fixed_expense"
    assert len(virtuals[0]["items"]) == 1
    assert virtuals[0]["items"][0]["label"] == "Auto"
    assert virtuals[0]["items"][0]["amount"] == 300
    assert virtuals[0]["items"][0]["is_virtual"] is True
    assert view["totals"]["fixed_expense"] == 300
    assert view["totals"]["investment_capacity"] == -300


def test_loans_added_to_user_fixed(tmp_path):
    engine = create_engine_and_tables(tmp_path / "ledger.db")
    with engine.begin() as conn:
        sec = conn.execute(insert(budget_sections).values(
            name="Salaires", section_type="income", position=0
        ))
        conn.execute(insert(budget_items).values(
            section_id=sec.inserted_primary_key[0], label="Salaire", amount=3000, position=0
        ))
        conn.execute(insert(loans).values(
            name="Immo", loan_type="immo", initial_capital=200000,
            monthly_payment=1200, total_months=240, start_date="2024-01-01",
        ))
    view = compose_budget(engine, today=date(2026, 4, 29))
    assert view["totals"]["income"] == 3000
    assert view["totals"]["fixed_expense"] == 1200  # uniquement la mensualité prêt
    assert view["totals"]["investment_capacity"] == 1800
