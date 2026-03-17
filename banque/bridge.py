#!/usr/bin/env python3
"""Banque Populaire bridge — JSON-lines over stdin/stdout."""

import json
import sys

from woob.core import Woob
from woob.exceptions import AppValidation, SentOTPQuestion

backend = None
woob_instance = None


def send(data):
    sys.stdout.write(json.dumps(data, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def handle_connect(params):
    global backend, woob_instance

    login = params.get("login", "")
    password = params.get("password", "")
    region = params.get("region", "")

    if not login or not password or not region:
        send({"type": "error", "message": "Missing login, password, or region"})
        return

    try:
        woob_instance = Woob()
        woob_instance.load_backend(
            "banquepopulaire",
            "bp",
            params={
                "login": login,
                "password": password,
                "cdetab": region,
                "request_information": "interactive",
            },
        )
        backend = woob_instance["bp"]

        try:
            accounts = list(backend.iter_accounts())
            send({
                "type": "connected",
                "accounts": [serialize_account(a) for a in accounts],
            })
        except SentOTPQuestion as e:
            send({"type": "2fa_sms", "message": str(e.message)})
        except AppValidation as e:
            send({"type": "2fa_app", "message": str(e.message)})

    except Exception as e:
        send({"type": "error", "message": str(e)})


def handle_validate_2fa(params):
    global backend

    if not backend:
        send({"type": "error", "message": "Not connected"})
        return

    method = params.get("method", "app")
    code = params.get("code", "")

    try:
        if method == "sms" and code:
            backend.config["code_sms"].set(code)
        else:
            backend.config["resume"].set("ok")

        accounts = list(backend.iter_accounts())
        send({
            "type": "connected",
            "accounts": [serialize_account(a) for a in accounts],
        })
    except AppValidation as e:
        send({"type": "2fa_app", "message": str(e.message)})
    except SentOTPQuestion as e:
        send({"type": "2fa_sms", "message": str(e.message)})
    except Exception as e:
        send({"type": "error", "message": str(e)})


def handle_get_accounts(_params):
    global backend

    if not backend:
        send({"type": "error", "message": "Not connected"})
        return

    try:
        accounts = list(backend.iter_accounts())
        send({
            "type": "accounts",
            "accounts": [serialize_account(a) for a in accounts],
        })
    except Exception as e:
        send({"type": "error", "message": str(e)})


def serialize_account(account):
    return {
        "id": account.id,
        "label": account.label,
        "balance": float(account.balance) if account.balance else 0,
        "currency": account.currency_text,
        "type": str(account.type),
    }


HANDLERS = {
    "connect": handle_connect,
    "validate_2fa": handle_validate_2fa,
    "get_accounts": handle_get_accounts,
}


def main():
    send({"type": "ready"})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            cmd = json.loads(line)
        except json.JSONDecodeError:
            send({"type": "error", "message": "Invalid JSON"})
            continue

        action = cmd.get("action", "")
        params = cmd.get("params", {})

        handler = HANDLERS.get(action)
        if handler:
            handler(params)
        else:
            send({"type": "error", "message": f"Unknown action: {action}"})


if __name__ == "__main__":
    main()
