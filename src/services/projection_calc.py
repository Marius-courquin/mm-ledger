# src/services/projection_calc.py
from datetime import date
from dateutil.relativedelta import relativedelta


def compute_projection(
    settings: dict,
    cash_initial: float,
    market_initial: float,
    loans: list[dict],
    today: date,
) -> list[dict]:
    """Boucle mois par mois sur horizon_years × 12.

    loans: liste de {"monthly_payment": float, "end_date": "YYYY-MM-DD"}.
    À chaque mois t, on calcule la somme des mensualités des prêts encore actifs
    (end_date > today + t mois).
    """
    horizon_months = settings["horizon_years"] * 12
    cash_monthly_rate = (1 + settings["cash_annual_rate"]) ** (1 / 12) - 1
    market_monthly_rate = (1 + settings["market_annual_rate"]) ** (1 / 12) - 1

    cash_t = float(cash_initial)
    market_t = float(market_initial)

    points: list[dict] = []
    for m in range(horizon_months):
        as_of = today + relativedelta(months=m + 1)
        loan_monthly_active = sum(
            float(l["monthly_payment"])
            for l in loans
            if date.fromisoformat(l["end_date"]) > as_of
        )
        cash_t = cash_t * (1 + cash_monthly_rate) + settings["cash_monthly_contribution"] - loan_monthly_active
        market_t = market_t * (1 + market_monthly_rate) + settings["market_monthly_contribution"]
        points.append({
            "month_offset": m + 1,
            "cash": round(cash_t, 2),
            "market": round(market_t, 2),
            "total": round(cash_t + market_t, 2),
            "loan_monthly_active": round(loan_monthly_active, 2),
        })
    return points
