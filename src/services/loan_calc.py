from datetime import date
from dateutil.relativedelta import relativedelta


def compute_loan_state(loan: dict, today: date) -> dict:
    """Calcule l'état courant d'un prêt depuis sa déclaration et la date du jour.

    Toutes les valeurs sont déterministes (pas de tracking de paiements individuels).
    """
    start = date.fromisoformat(loan["start_date"])
    total_months = int(loan["total_months"])
    monthly = float(loan["monthly_payment"])

    end_date = start + relativedelta(months=total_months)

    if today < start:
        months_paid = 0
    else:
        delta = relativedelta(today, start)
        months_paid = delta.years * 12 + delta.months
    months_paid = max(0, min(months_paid, total_months))
    months_remaining = total_months - months_paid
    amount_remaining = monthly * months_remaining
    progress_pct = (months_paid / total_months * 100.0) if total_months > 0 else 0.0
    archived = bool(loan.get("archived"))
    is_active = (months_remaining > 0) and not archived

    return {
        "end_date": end_date.isoformat(),
        "months_paid": months_paid,
        "months_remaining": months_remaining,
        "amount_remaining": round(amount_remaining, 2),
        "progress_pct": round(progress_pct, 2),
        "is_active": is_active,
    }
