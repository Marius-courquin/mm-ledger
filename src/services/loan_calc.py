from datetime import date, datetime, timezone
from decimal import Decimal
from dateutil.relativedelta import relativedelta

BANK_BALANCE_FRESHNESS_DAYS = 7


def compute_loan_state(
    loan: dict,
    today: date,
    linked_balance: Decimal | None = None,
    balance_as_of: datetime | None = None,
) -> dict:
    """Calcule l'état courant d'un prêt depuis sa déclaration et la date du jour.

    Toutes les valeurs sont déterministes (pas de tracking de paiements individuels).

    Si linked_balance + balance_as_of sont fournis ET frais (< 7 jours),
    amount_remaining est lu depuis le solde bancaire (amount_source = "bank").
    Sinon, calcul calendaire pur (amount_source = "calendar").
    """
    start = (
        loan["start_date"]
        if isinstance(loan["start_date"], date)
        else date.fromisoformat(loan["start_date"])
    )
    end_date = start + relativedelta(months=loan["total_months"])
    months_paid_calendar = 0
    if today >= start:
        delta = relativedelta(today, start)
        months_paid_calendar = delta.years * 12 + delta.months
    months_paid_calendar = max(0, min(months_paid_calendar, loan["total_months"]))
    months_remaining_calendar = loan["total_months"] - months_paid_calendar
    monthly = float(loan["monthly_payment"])

    use_bank = (
        linked_balance is not None
        and balance_as_of is not None
        and (datetime.now(timezone.utc) - balance_as_of).days < BANK_BALANCE_FRESHNESS_DAYS
        and monthly > 0
    )

    if use_bank:
        amount_remaining = float(abs(linked_balance))
        months_remaining = int(round(amount_remaining / monthly))
        months_remaining = max(0, min(months_remaining, loan["total_months"]))
        amount_source = "bank"
    else:
        amount_remaining = round(monthly * months_remaining_calendar, 2)
        months_remaining = months_remaining_calendar
        amount_source = "calendar"

    progress_pct = (
        (loan["total_months"] - months_remaining) / loan["total_months"] * 100
        if loan["total_months"] else 0
    )
    is_active = months_remaining > 0 and not loan.get("archived")

    return {
        "end_date": end_date.isoformat(),
        "months_paid": loan["total_months"] - months_remaining,
        "months_remaining": months_remaining,
        "amount_remaining": amount_remaining,
        "progress_pct": round(progress_pct, 1),
        "is_active": is_active,
        "amount_source": amount_source,
    }
