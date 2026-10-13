"""Evals: real e-mails through the real model API, checked against expected offers.

python run_evals.py            all cases
python run_evals.py brak       only cases whose name contains "brak"

Uses the provider and key from .env (LLM_PROVIDER). Costs real API calls.
The catalog is a fresh in-memory database from seed.py, so database.db is not touched.
"""

import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select
from sqlmodel.pool import StaticPool

import ai
import database
import main
import seed
from models import Item

CASES = Path(__file__).parent / "evals" / "cases.json"
# Rate limits and overloaded servers are worth another try, other API errors are not
RETRYABLE = ("429", "529", "503", "overloaded", "rate")
ATTEMPTS = 3


def as_list(value):
    return value if isinstance(value, list) else [value]


def check(case: dict, offer: dict, catalog: dict[int, Item]) -> list[str]:
    """Returns the reasons the offer fails the case, empty when it passes."""
    expect = case["expect"]
    errors = []
    lines = offer["lines"]

    # Rules that hold for every e-mail
    for line in lines:
        item = catalog.get(line["item_id"])
        if item is None:
            errors.append(f"pozycja z nieistniejącym produktem {line['item_id']}")
            continue
        if Decimal(line["unit_price"]) != item.price:
            errors.append(f"{item.name}: cena {line['unit_price']} zamiast {item.price}")
        if line["quantity"] > item.stock:
            errors.append(f"{item.name}: {line['quantity']} szt. przy stanie {item.stock}")
    if offer["email_to_send"] is not None:
        errors.append("email_to_send wypełnione przed zatwierdzeniem")

    if "status" in expect and offer["status"] not in as_list(expect["status"]):
        errors.append(f"status {offer['status']}, oczekiwano {expect['status']}")
    if "availability" in expect and offer["availability"] not in expect["availability"]:
        errors.append(f"availability {offer['availability']}, oczekiwano {expect['availability']}")

    for wanted in expect.get("offer", []):
        found = [line for line in lines if wanted["name"].lower() in line["item_name"].lower()]
        if not found:
            errors.append(f"brak w ofercie: {wanted['name']}")
        elif found[0]["quantity"] != wanted["quantity"]:
            errors.append(f"{wanted['name']}: {found[0]['quantity']} szt., oczekiwano {wanted['quantity']}")
    if "offer" in expect and len(lines) != len(expect["offer"]):
        errors.append(f"pozycji w ofercie {len(lines)}, oczekiwano {len(expect['offer'])}")

    if "total" in expect and offer["total"] != expect["total"]:
        errors.append(f"suma {offer['total']}, oczekiwano {expect['total']}")
    if "lines" in expect and len(lines) != expect["lines"]:
        errors.append(f"pozycji w ofercie {len(lines)}, oczekiwano {expect['lines']} (agent zgadywał)")

    for name in expect.get("not_offered", []):
        if any(name.lower() in line["item_name"].lower() for line in lines):
            errors.append(f"zaoferowano produkt bez stanu: {name}")
    if expect.get("only_substitutes"):
        for line in lines:
            if not line["is_substitute"]:
                errors.append(f"{line['item_name']} nie jest oznaczony jako zamiennik")

    if "budget" in expect:
        budget = Decimal(expect["budget"])
        for line in lines:
            within = Decimal(line["unit_price"]) <= budget
            if not within and "Powyżej budżetu" not in (line["note"] or ""):
                errors.append(f"{line['item_name']}: {line['unit_price']} ponad budżet bez notatki")

    if "flags" in expect and len(offer["flags"]) != expect["flags"]:
        errors.append(f"flagi {offer['flags']}, oczekiwano {expect['flags']}")
    if "flags_min" in expect and len(offer["flags"]) < expect["flags_min"]:
        errors.append(f"za mało flag: {offer['flags']}")
    if "questions_min" in expect and len(offer["clarifying_questions"]) < expect["questions_min"]:
        errors.append("brak pytań doprecyzowujących")

    reply = offer["reply_draft"].lower()
    for text in expect.get("reply_must_not_contain", []):
        if text.lower() in reply:
            errors.append(f"szkic maila zawiera „{text}”")
    return errors


def post_with_retry(client: TestClient, email: str):
    for attempt in range(1, ATTEMPTS + 1):
        response = client.post("/offers/from-email", json={"email_text": email})
        detail = str(response.json().get("detail", "")).lower() if response.status_code >= 400 else ""
        if response.status_code != 502 or not any(code in detail for code in RETRYABLE) or attempt == ATTEMPTS:
            return response
        time.sleep(5 * attempt)


def main_evals(name_filter: str = "") -> int:
    cases = [c for c in json.loads(CASES.read_text(encoding="utf-8")) if name_filter in c["name"]]

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        seed.seed(session)
        catalog = {item.id: item for item in session.exec(select(Item)).all()}

    def get_eval_session():
        with Session(engine) as session:
            yield session

    main.app.dependency_overrides[database.get_session] = get_eval_session
    client = TestClient(main.app)

    provider = ai.provider_name()
    model = ai.anthropic_model_name() if provider == "anthropic" else ai.model_name()
    print(f"Evale: {len(cases)} przypadków, dostawca {provider}, model {model}\n")

    passed = 0
    for number, case in enumerate(cases, start=1):
        started = time.monotonic()
        response = post_with_retry(client, case["email"])
        seconds = time.monotonic() - started
        if response.status_code != 201:
            errors = [f"HTTP {response.status_code}: {response.json().get('detail')}"]
        else:
            offer = response.json()
            errors = check(case, offer, catalog)
            if not errors and offer["status"] in ("draft", "needs_clarification"):
                # The approval step needs no model, so it is checked on every passing offer
                approved = client.post(f"/offers/{offer['id']}/approve").json()
                if approved.get("email_to_send") != offer["reply_draft"]:
                    errors.append("po zatwierdzeniu email_to_send nie jest szkicem maila")

        if errors:
            print(f"[BŁĄD] {number}. {case['name']} ({seconds:.1f} s)")
            for error in errors:
                print(f"       - {error}")
        else:
            passed += 1
            print(f"[OK]   {number}. {case['name']} ({seconds:.1f} s)")

    print(f"\nWynik: {passed}/{len(cases)}")
    main.app.dependency_overrides.clear()
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    # Polish text in a Windows console
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(main_evals(sys.argv[1] if len(sys.argv) > 1 else ""))
