import json
import os
from datetime import date
from decimal import Decimal

from woob.core import Woob
from woob.exceptions import AppValidation, SentOTPQuestion

try:
    from config import (
        BANQUE_POPULAIRE_LOGIN,
        BANQUE_POPULAIRE_PASSWORD,
        BANQUE_POPULAIRE_REGION,
    )
except ImportError:
    print("Erreur: copier config.example.py en config.py et remplir vos identifiants")
    exit(1)

OUTPUT_PATH = os.path.join(os.path.dirname(__file__), "..", "src", "data", "bank_data.json")


def connect():
    w = Woob()
    w.load_backend(
        "banquepopulaire",
        "bp",
        params={
            "login": BANQUE_POPULAIRE_LOGIN,
            "password": BANQUE_POPULAIRE_PASSWORD,
            "cdetab": BANQUE_POPULAIRE_REGION,
            "request_information": "interactive",
        },
    )

    backend = w["bp"]

    try:
        accounts = list(backend.iter_accounts())
    except SentOTPQuestion as e:
        print(f"Code SMS requis: {e.message}")
        code = input("Entrez le code reçu par SMS: ")
        backend.config["code_sms"].set(code)
        accounts = list(backend.iter_accounts())
    except AppValidation as e:
        print(f"\n{e.message}")
        input("\nAppuyez sur Entrée après avoir validé sur l'appli...")
        backend.config["resume"].set("ok")
        accounts = list(backend.iter_accounts())

    return backend, accounts


def serialize(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    return str(obj)


def fetch_all(backend, accounts):
    result = {
        "fetched_at": date.today().isoformat(),
        "accounts": [],
    }

    print("\nComptes Banque Populaire:")
    print("-" * 60)

    for account in accounts:
        print(f"{account.label:>40}  {account.balance:>10} {account.currency_text}")

        account_data = {
            "id": account.id,
            "label": account.label,
            "balance": serialize(account.balance),
            "currency": account.currency_text,
            "type": str(account.type),
            "transactions": [],
        }

        # Fetch transaction history
        try:
            for tr in backend.iter_history(account):
                account_data["transactions"].append({
                    "date": serialize(tr.date),
                    "rdate": serialize(tr.rdate) if tr.rdate else None,
                    "label": tr.label,
                    "amount": serialize(tr.amount),
                    "type": str(tr.type),
                })
        except Exception as e:
            print(f"  (historique indisponible: {e})")

        result["accounts"].append(account_data)

    print("-" * 60)
    return result


def main():
    backend, accounts = connect()
    data = fetch_all(backend, accounts)

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    total_tx = sum(len(a["transactions"]) for a in data["accounts"])
    print(f"\n{len(data['accounts'])} comptes, {total_tx} transactions")
    print(f"Sauvegardé dans {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
