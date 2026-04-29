from datetime import date
from sqlalchemy import select
from sqlalchemy.engine import Engine

from src.db.models import budget_sections, budget_items, loans
from src.services.loan_calc import compute_loan_state


def compose_budget(engine: Engine, today: date) -> dict:
    """Assemble la vue Budget : sections user + section virtuelle Prêts + totaux."""
    with engine.connect() as conn:
        sec_rows = conn.execute(
            select(budget_sections).order_by(budget_sections.c.position, budget_sections.c.id)
        ).fetchall()
        item_rows = conn.execute(
            select(budget_items).order_by(budget_items.c.position, budget_items.c.id)
        ).fetchall()
        loan_rows = conn.execute(select(loans).where(loans.c.archived == 0)).fetchall()

    items_by_section: dict[int, list[dict]] = {}
    for r in item_rows:
        items_by_section.setdefault(r.section_id, []).append({
            "id": r.id, "label": r.label, "amount": float(r.amount),
            "position": r.position, "is_virtual": False,
        })

    sections: list[dict] = []
    for s in sec_rows:
        sections.append({
            "id": s.id, "name": s.name, "section_type": s.section_type,
            "position": s.position, "is_virtual": False,
            "items": items_by_section.get(s.id, []),
        })

    # Section virtuelle Prêts (un item par prêt actif)
    virtual_items = []
    for l in loan_rows:
        st = compute_loan_state({
            "start_date": l.start_date, "total_months": l.total_months,
            "monthly_payment": l.monthly_payment, "initial_capital": l.initial_capital,
            "archived": l.archived,
        }, today)
        if st["is_active"]:
            virtual_items.append({
                "id": f"virtual:loan:{l.id}",
                "label": l.name,
                "amount": float(l.monthly_payment),
                "position": 0,
                "is_virtual": True,
            })
    if virtual_items:
        sections.insert(0, {
            "id": "virtual:loans", "name": "Prêts",
            "section_type": "fixed_expense", "position": -1,
            "is_virtual": True, "items": virtual_items,
        })

    income = sum(it["amount"] for s in sections if s["section_type"] == "income" for it in s["items"])
    fixed = sum(it["amount"] for s in sections if s["section_type"] == "fixed_expense" for it in s["items"])
    variable = sum(it["amount"] for s in sections if s["section_type"] == "variable_expense" for it in s["items"])
    expense = fixed + variable
    capacity = income - expense

    return {
        "sections": sections,
        "totals": {
            "income": round(income, 2),
            "fixed_expense": round(fixed, 2),
            "variable_expense": round(variable, 2),
            "expense": round(expense, 2),
            "investment_capacity": round(capacity, 2),
        },
    }
