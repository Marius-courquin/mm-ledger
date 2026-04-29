from datetime import date
from src.services.projection_calc import compute_projection


def _settings(**kw):
    base = {
        "cash_annual_rate": 0.02,
        "market_annual_rate": 0.05,
        "cash_monthly_contribution": 0,
        "market_monthly_contribution": 0,
        "horizon_years": 10,
    }
    base.update(kw)
    return base


def test_zero_capital_zero_rate_zero_contrib():
    points = compute_projection(_settings(cash_annual_rate=0, market_annual_rate=0),
                                cash_initial=0, market_initial=0, loans=[],
                                today=date(2026, 4, 29))
    assert len(points) == 120  # 10 ans
    assert points[-1]["total"] == 0


def test_market_growth():
    """1000€ marché à 5%/an pendant 1 an → ~1051€."""
    points = compute_projection(_settings(market_annual_rate=0.05, horizon_years=1),
                                cash_initial=0, market_initial=1000, loans=[],
                                today=date(2026, 4, 29))
    assert len(points) == 12
    assert 1049 < points[-1]["market"] < 1052
    assert points[-1]["cash"] == 0


def test_cash_with_monthly_contribution():
    """0€ cash + 100€/mois pendant 12 mois sans intérêt → 1200€."""
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0,
                  cash_monthly_contribution=100, horizon_years=1),
        cash_initial=0, market_initial=0, loans=[], today=date(2026, 4, 29))
    assert points[-1]["cash"] == 1200


def test_loan_monthly_deducted_from_cash():
    """Mensualité de prêt déduite du cash chaque mois."""
    loan = {"monthly_payment": 500, "end_date": "2030-01-01"}
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=10000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    # 12 mois de 500€ déduits → 10000 - 6000 = 4000
    assert points[-1]["cash"] == 4000
    assert points[-1]["loan_monthly_active"] == 500


def test_loan_ends_during_horizon():
    """Prêt qui se termine dans 6 mois ne se déduit plus après."""
    loan = {"monthly_payment": 500, "end_date": "2026-10-29"}  # ~6 mois après today
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=10000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    # le 12e mois, le prêt n'est plus actif
    last = points[-1]
    assert last["loan_monthly_active"] == 0
    # cash final > 4000 puisque 6 mois sans déduction
    assert last["cash"] > 4000


def test_negative_cash_allowed():
    """Cash peut devenir négatif sans erreur."""
    loan = {"monthly_payment": 5000, "end_date": "2040-01-01"}
    points = compute_projection(
        _settings(cash_annual_rate=0, market_annual_rate=0, horizon_years=1),
        cash_initial=1000, market_initial=0, loans=[loan], today=date(2026, 4, 29))
    assert points[-1]["cash"] < 0  # non bloquant


def test_horizon_30_years_yields_360_points():
    points = compute_projection(_settings(horizon_years=30),
                                cash_initial=0, market_initial=0, loans=[], today=date(2026, 4, 29))
    assert len(points) == 360
