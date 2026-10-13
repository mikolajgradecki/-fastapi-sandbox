"""The Anthropic provider: same flow as Gemini, with a fake Anthropic client."""

import json
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

import ai
import main

client = TestClient(main.app)


def text_block(text):
    return SimpleNamespace(type="text", text=text)


def tool_use(block_id, name, args):
    return SimpleNamespace(type="tool_use", id=block_id, name=name, input=args)


def message(*content, stop_reason="tool_use"):
    return SimpleNamespace(content=list(content), stop_reason=stop_reason)


def parsed(spec, stop_reason="end_turn"):
    return SimpleNamespace(
        content=[text_block(json.dumps(spec))],
        stop_reason=stop_reason,
        parsed_output=ai.RequestSpec.model_validate(spec) if spec is not None else None,
    )


class FakeMessages:
    """Plays back prepared responses for messages.parse and messages.create."""

    def __init__(self, parse_responses, create_responses):
        self.parse_responses = list(parse_responses)
        self.create_responses = list(create_responses)
        self.parse_calls = []
        self.create_calls = []

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self._next(self.parse_responses)

    def create(self, **kwargs):
        # Copy: the agent keeps appending to the same messages list
        self.create_calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self._next(self.create_responses)

    @staticmethod
    def _next(responses):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeAnthropic:
    def __init__(self, parse_responses=(), create_responses=()):
        self.messages = FakeMessages(parse_responses, create_responses)


def use_anthropic(fake):
    main.app.dependency_overrides[main.ai_client] = lambda: ai.AnthropicProvider(fake)
    return fake


@pytest.fixture
def catalog():
    products = {
        "Dell": {"name": "Monitor Dell P2725H 27 FHD IPS", "price": "899.00", "category": "monitory", "stock": 45},
        "Laptop": {"name": "Laptop HP ProBook 450 G11 15.6 i5 16GB 512GB", "price": "3599.00", "category": "laptopy", "stock": 32},
        "Stacja": {"name": "Stacja dokująca Dell WD19S USB-C 130W", "price": "749.00", "category": "stacje-dokujace", "stock": 3},
    }
    return {key: client.post("/items", json=product).json() for key, product in products.items()}


SPEC = {
    "lines": [
        {"description": "laptop", "quantity": 12, "max_unit_price": 4000},
        {"description": "monitor 27 cali", "quantity": 12},
    ],
    "deadline": "30.10",
}
EMAIL = "Potrzebujemy 12 laptopów do 4000 zł netto i 12 monitorów 27 cali. Dostawa do 30.10."


def post_email(text=EMAIL):
    return client.post("/offers/from-email", json={"email_text": text})


def test_anthropic_offer_happy_path(catalog):
    laptop, monitor = catalog["Laptop"]["id"], catalog["Dell"]["id"]
    fake = use_anthropic(
        FakeAnthropic(
            [parsed(SPEC)],
            [
                message(
                    text_block("Szukam produktów."),
                    tool_use("t1", "search_items", {"category": "laptopy", "max_price": 4000}),
                    tool_use("t2", "search_items", {"name": "monitor 27"}),
                ),
                message(
                    tool_use(
                        "t3",
                        "submit_selection",
                        {
                            "choices": [
                                {"request_index": 0, "item_id": laptop, "unit_price": 3599},
                                {"request_index": 1, "item_id": monitor, "unit_price": 899},
                            ]
                        },
                    )
                ),
            ],
        )
    )

    response = post_email()
    assert response.status_code == 201
    offer = response.json()
    assert offer["status"] == "complete"
    assert [line["item_id"] for line in offer["lines"]] == [laptop, monitor]
    assert offer["total"] == "53976.00"

    # Step 1: structured output into RequestSpec, the e-mail in its data block
    extract = fake.messages.parse_calls[0]
    assert extract["model"] == "claude-haiku-5-5"
    assert extract["output_format"] is ai.RequestSpec
    assert extract["system"] == ai.EXTRACT_INSTRUCTION
    assert extract["messages"][0]["content"] == f"<email_klienta>\n{EMAIL}\n</email_klienta>"

    # Step 2: the same tools as Gemini, and both tool results came back in one user message
    first, second = fake.messages.create_calls
    assert [tool["name"] for tool in first["tools"]] == ["search_items", "get_item", "submit_selection"]
    assert "monitory" in first["system"]
    results = second["messages"][-1]
    assert results["role"] == "user"
    assert [r["tool_use_id"] for r in results["content"]] == ["t1", "t2"]
    laptops = json.loads(results["content"][0]["content"])["items"]
    assert [item["name"] for item in laptops] == ["Laptop HP ProBook 450 G11 15.6 i5 16GB 512GB"]
    assert results["content"][0]["is_error"] is False
    # The model's turn went back whole
    assert second["messages"][1]["content"][0].text == "Szukam produktów."


def test_anthropic_invented_id_and_lowered_price_are_caught(catalog):
    use_anthropic(
        FakeAnthropic(
            [parsed(SPEC)],
            [
                message(
                    tool_use(
                        "t1",
                        "submit_selection",
                        {
                            "choices": [
                                {"request_index": 0, "item_id": 777, "unit_price": 1},
                                {"request_index": 1, "item_id": catalog["Dell"]["id"], "unit_price": 1},
                            ]
                        },
                    )
                )
            ],
        )
    )

    offer = post_email().json()
    assert offer["missing"][0]["reason"] == "Produkt o id 777 nie istnieje w katalogu."
    assert offer["lines"][0]["unit_price"] == "899.00"
    assert offer["total"] == "10788.00"


def test_anthropic_quantity_above_stock_goes_to_missing(catalog):
    spec = {"lines": [{"description": "stacja dokująca", "quantity": 12}]}
    use_anthropic(
        FakeAnthropic(
            [parsed(spec)],
            [message(tool_use("t1", "submit_selection", {"choices": [{"request_index": 0, "item_id": catalog["Stacja"]["id"]}]}))],
        )
    )

    offer = post_email().json()
    assert offer["status"] == "unavailable"
    assert offer["missing"][0]["reason"] == "Stacja dokująca Dell WD19S USB-C 130W: na stanie 3 szt., zapytanie o 12 szt."


def test_anthropic_tool_errors_go_back_with_is_error(catalog):
    spec = {"lines": [{"description": "monitor", "quantity": 1}]}
    fake = use_anthropic(
        FakeAnthropic(
            [parsed(spec)],
            [
                message(tool_use("t1", "get_item", {"id": 999})),
                message(tool_use("t2", "submit_selection", {"choices": [{"request_index": "x"}]})),
                message(tool_use("t3", "submit_selection", {"choices": [{"request_index": 0, "item_id": catalog["Dell"]["id"]}]})),
            ],
        )
    )

    assert post_email().json()["status"] == "complete"
    not_found = fake.messages.create_calls[1]["messages"][-1]["content"][0]
    assert not_found["is_error"] is True
    assert json.loads(not_found["content"]) == {"error": "Nie ma produktu o id 999"}
    bad_format = fake.messages.create_calls[2]["messages"][-1]["content"][0]
    assert bad_format["is_error"] is True
    assert "Zły format wyboru" in bad_format["content"]


def test_anthropic_text_answer_gets_one_reminder(catalog):
    spec = {"lines": [{"description": "monitor", "quantity": 1}]}
    fake = use_anthropic(
        FakeAnthropic(
            [parsed(spec)],
            [
                message(text_block("Proponuję monitor Dell."), stop_reason="end_turn"),
                message(tool_use("t1", "submit_selection", {"choices": [{"request_index": 0, "item_id": catalog["Dell"]["id"]}]})),
            ],
        )
    )

    assert post_email().json()["status"] == "complete"
    reminder = fake.messages.create_calls[1]["messages"][-1]
    assert reminder == {"role": "user", "content": "Zakończ, wywołując submit_selection z wyborem dla każdej pozycji."}


def api_error(status, message_text):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx2.Response(status, request=request, json={"type": "error", "error": {"message": message_text}})
    return anthropic.APIStatusError(message_text, response=response, body=None)


@pytest.mark.parametrize(
    "parse_responses, create_responses, detail",
    [
        ([parsed(None)], [], "Model zwrócił zapytanie w złym formacie."),
        ([parsed(SPEC, stop_reason="refusal")], [], "Model odmówił odpowiedzi."),
        ([parsed(SPEC, stop_reason="max_tokens")], [], "Odpowiedź modelu została ucięta (limit tokenów)."),
        ([api_error(429, "Rate limited")], [], "Anthropic API zwróciło błąd 429: Rate limited"),
        (
            [parsed(SPEC)],
            [message(text_block("Nie wiem."), stop_reason="end_turn")] * 2,
            "Model nie wywołał żadnego narzędzia.",
        ),
        (
            [parsed(SPEC)],
            [message(tool_use("t", "search_items", {"name": "monitor"}))] * ai.MAX_TOOL_ROUNDS,
            f"Model nie zakończył doboru produktów w {ai.MAX_TOOL_ROUNDS} krokach.",
        ),
    ],
)
def test_anthropic_failures_return_502(catalog, parse_responses, create_responses, detail):
    use_anthropic(FakeAnthropic(parse_responses, create_responses))

    response = post_email()
    assert response.status_code == 502
    assert response.json() == {"detail": detail}


# Choosing the provider


def test_provider_from_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    assert isinstance(ai.get_client(), ai.GeminiProvider)

    monkeypatch.setenv("LLM_PROVIDER", " Anthropic ")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic")
    assert isinstance(ai.get_client(), ai.AnthropicProvider)


def test_anthropic_model_can_be_overridden(monkeypatch):
    assert ai.anthropic_model_name() == "claude-haiku-5-5"
    monkeypatch.setenv("ANTHROPIC_MODEL", "claude-sonnet-5-5")
    assert ai.anthropic_model_name() == "claude-sonnet-5-5"


@pytest.mark.parametrize(
    "provider, detail",
    [
        ("anthropic", "Brak ANTHROPIC_API_KEY. Dodaj klucz do pliku .env albo do zmiennych środowiskowych."),
        ("openai", "Nieznany LLM_PROVIDER: openai. Dozwolone: gemini, anthropic."),
    ],
)
def test_provider_config_errors_return_503(monkeypatch, provider, detail):
    monkeypatch.setenv("LLM_PROVIDER", provider)

    response = post_email()
    assert response.status_code == 503
    assert response.json() == {"detail": detail}


def test_error_messages_never_contain_the_key(monkeypatch):
    secret = "sk-ant-test-secret-value"
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    use_anthropic(FakeAnthropic([api_error(401, "invalid x-api-key")]))

    response = post_email()
    assert response.status_code == 502
    assert secret not in response.text
