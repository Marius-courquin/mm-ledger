from datetime import date, datetime, timezone, timedelta
from decimal import Decimal
from src.services.loan_calc import compute_loan_state


def _loan(start="2020-01-01", total_months=240, monthly=1200, capital=250000, archived=False):
    return {
        "start_date": start,
        "total_months": total_months,
        "monthly_payment": monthly,
        "initial_capital": capital,
        "archived": int(archived),
    }


def test_state_in_progress():
    """Prêt 20 ans démarré il y a 6 ans, mensualité 1200."""
    state = compute_loan_state(_loan(start="2020-01-01"), today=date(2026, 1, 1))
    assert state["months_paid"] == 72
    assert state["months_remaining"] == 168
    assert state["amount_remaining"] == 168 * 1200
    assert state["end_date"] == "2040-01-01"
    assert 29.5 < state["progress_pct"] < 30.5
    assert state["is_active"] is True


def test_state_future_start():
    """Prêt qui commence demain → 0 payé."""
    state = compute_loan_state(_loan(start="2030-01-01"), today=date(2026, 1, 1))
    assert state["months_paid"] == 0
    assert state["months_remaining"] == 240
    assert state["progress_pct"] == 0.0
    assert state["is_active"] is True


def test_state_finished():
    """Prêt arrivé à terme."""
    state = compute_loan_state(_loan(start="2000-01-01", total_months=12), today=date(2026, 1, 1))
    assert state["months_paid"] == 12
    assert state["months_remaining"] == 0
    assert state["amount_remaining"] == 0
    assert state["progress_pct"] == 100.0
    assert state["is_active"] is False


def test_state_today_is_start():
    state = compute_loan_state(_loan(start="2026-01-01", total_months=12), today=date(2026, 1, 1))
    assert state["months_paid"] == 0
    assert state["months_remaining"] == 12


def test_state_archived_not_active():
    state = compute_loan_state(_loan(archived=True), today=date(2026, 1, 1))
    assert state["is_active"] is False


def test_state_total_months_one():
    state = compute_loan_state(_loan(start="2025-12-01", total_months=1, monthly=500), today=date(2026, 1, 1))
    assert state["months_paid"] == 1
    assert state["months_remaining"] == 0
    assert state["progress_pct"] == 100.0


def test_compute_with_recent_bank_balance_uses_bank():
    loan = {
        "start_date": date(2026, 1, 1),
        "total_months": 24,
        "monthly_payment": 200.0,
        "initial_capital": 4000.0,
        "archived": 0,
    }
    state = compute_loan_state(
        loan, today=date(2026, 4, 30),
        linked_balance=Decimal("-3500.00"),
        balance_as_of=datetime.now(timezone.utc),
    )
    assert state["amount_source"] == "bank"
    assert state["amount_remaining"] == 3500.0
    assert state["months_remaining"] in (17, 18)


def test_compute_with_stale_bank_balance_falls_back_to_calendar():
    loan = {"start_date": date(2026, 1, 1), "total_months": 24,
            "monthly_payment": 200.0, "initial_capital": 4000.0, "archived": 0}
    stale = datetime.now(timezone.utc) - timedelta(days=30)
    state = compute_loan_state(
        loan, today=date(2026, 4, 30),
        linked_balance=Decimal("-3500.00"), balance_as_of=stale,
    )
    assert state["amount_source"] == "calendar"


def test_compute_without_link_uses_calendar():
    loan = {"start_date": date(2026, 1, 1), "total_months": 24,
            "monthly_payment": 200.0, "initial_capital": 4000.0, "archived": 0}
    state = compute_loan_state(loan, today=date(2026, 4, 30))
    assert state["amount_source"] == "calendar"
