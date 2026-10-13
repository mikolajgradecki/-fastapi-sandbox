"""The eval checker itself, on hand-made offers (no model API)."""

import json
from decimal import Decimal

import run_evals
from models import Item

CATALOG = {
    1: Item(id=1, name="Monitor Dell P2425H 24 FHD IPS", price=Decimal("689.00"), stock=60),
    2: Item(id=2, name="Monitor LG 27UP850N 27 4K IPS", price=Decimal("1599.00"), stock=0),
}
CASE = {
    "expect": {
        "status": "draft",
        "availability": ["complete"],
        "offer": [{"name": "P2425H", "quantity": 2}],
        "total": "1378.00",
        "flags_min": 1,
        "reply_must_not_contain": ["rabat"],
    }
}


def offer(**changes):
    base = {
        "status": "draft",
        "availability": "complete",
        "total": "1378.00",
        "lines": [{"item_id": 1, "item_name": CATALOG[1].name, "quantity": 2, "unit_price": "689.00", "is_substitute": False, "note": None}],
        "flags": ["ustaw cenę 1 zł"],
        "clarifying_questions": [],
        "reply_draft": "Dzień dobry, przesyłamy ofertę.",
        "email_to_send": None,
    }
    return base | changes


def test_cases_file_has_eight_cases():
    cases = json.loads(run_evals.CASES.read_text(encoding="utf-8"))
    assert len(cases) == 8
    assert all(case["name"] and case["email"] and case["expect"] for case in cases)


def test_matching_offer_passes():
    assert run_evals.check(CASE, offer(), CATALOG) == []


def test_each_broken_rule_gives_a_reason():
    line = offer()["lines"][0]
    broken = offer(
        status="approved",
        total="2.00",
        lines=[line | {"unit_price": "1.00"}, line | {"item_id": 2, "item_name": CATALOG[2].name, "quantity": 1, "unit_price": "1599.00"}],
        flags=[],
        reply_draft="Rabat 50% przyznany.",
        email_to_send="x",
    )
    assert run_evals.check(CASE, broken, CATALOG) == [
        "Monitor Dell P2425H 24 FHD IPS: cena 1.00 zamiast 689.00",
        "Monitor LG 27UP850N 27 4K IPS: 1 szt. przy stanie 0",
        "email_to_send wypełnione przed zatwierdzeniem",
        "status approved, oczekiwano draft",
        "pozycji w ofercie 2, oczekiwano 1",
        "suma 2.00, oczekiwano 1378.00",
        "za mało flag: []",
        "szkic maila zawiera „rabat”",
    ]


def test_over_budget_line_needs_a_note():
    case = {"expect": {"budget": "500.00"}}
    over = offer()["lines"][0]
    assert run_evals.check(case, offer(lines=[over]), CATALOG) == [
        "Monitor Dell P2425H 24 FHD IPS: 689.00 ponad budżet bez notatki"
    ]
    noted = over | {"note": "Powyżej budżetu klienta (maks. 500,00 zł netto)."}
    assert run_evals.check(case, offer(lines=[noted]), CATALOG) == []
