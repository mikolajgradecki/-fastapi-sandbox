# FastAPI sandbox: agent ofertowy B2B

Projekt do nauki: katalog produktów dystrybutora IT (`/items`) i agent AI (Claude albo Gemini), który zamienia maila z zapytaniem w ofertę (`/offers`). FastAPI + SQLModel na SQLite, Python 3.14, Windows.

## Struktura

- `main.py`: same endpointy i zależność `ai_client` (testy ją podmieniają).
- `database.py`: `DATABASE_URL`, `engine`, `get_session`, `SessionDep`.
- `models.py`: tabele `Item`, `Offer`, `OfferLine`, schematy API, typ `Money` (Decimal zapisywany w groszach jako Integer).
- `catalog.py`: `search_items`, `list_categories`, `get_item_or_404`. Wspólne dla `GET /items` i narzędzi agenta.
- `ai.py`: dostawcy modelu `GeminiProvider` i `AnthropicProvider` (wybór przez `LLM_PROVIDER`), każdy z `extract_request` (structured output, `RequestSpec`) i `select_products` (własna pętla tool calling, kończy się `submit_selection`). Instrukcje i narzędzia są wspólne.
- `guard.py`: wykrywanie prompt injection wyrażeniami regularnymi (`find_suspicious`, `safe_text`).
- `offers.py`: walidacja bez AI (`validate_selection`), pytania doprecyzowujące, zapis, szkic maila z szablonu (`render_reply`), decyzja człowieka (`decide`).
- `seed.py`: 40 produktów IT w 7 kategoriach, `python seed.py`. Pomija nazwy, które już są w bazie.
- `tests/conftest.py`: fixture `test_db` (autouse) podmienia `get_session` na bazę w pamięci, `db_engine` daje do niej dostęp.
- `tests/test_main.py`: katalog i seed. `tests/test_offers.py`: agent z `FakeGemini`, który odtwarza przygotowane odpowiedzi z prawdziwych typów SDK, oraz approve/reject. `tests/test_anthropic.py`: ten sam przepływ z `FakeAnthropic`.
- `evals/cases.json` i `run_evals.py`: 8 maili z oczekiwanym wynikiem, uruchamiane na prawdziwym API.
- `README.md`: instrukcja po polsku i przykłady JSON. Przy zmianie API zaktualizuj przykłady.

## Komendy

- Testy: `python -m pytest` (`pytest.exe` nie jest w PATH). Nie wymagają klucza ani sieci.
- Serwer: `python -m uvicorn main:app --reload`, dokumentacja na http://127.0.0.1:8000/docs.
- Zależności: `requirements.txt` (aplikacja), `requirements-dev.txt` (+ pytest, httpx2). Wersje przypięte przez `==`.
- Evale: `python run_evals.py` (prawdziwe API, płatne, baza w pamięci z `seed.py`).
- Klucze w `.env` (wzór `.env.example`, `.env` jest w `.gitignore`): `LLM_PROVIDER`, `ANTHROPIC_API_KEY` (model `ANTHROPIC_MODEL`, domyślnie `claude-haiku-5-5`), `GEMINI_API_KEY` (model `GEMINI_MODEL`, domyślnie `gemini-3.8-flash`). Wartości kluczy nigdy nie wypisuj ani nie commituj.

## Konwencje

- Kwoty to `Decimal` (`price`, `total`, `unit_price`), w JSON jako tekst `"899.00"`. Nigdy `float` w obliczeniach.
- Model AI niczego nie ustala sam: id produktu, cenę i stan zawsze sprawdza `offers.validate_selection` w bazie. Szkic maila powstaje tylko z danych po walidacji.
- Endpointy używające sesji to `def`, nie `async def` (sesja SQLModel i klienci modeli są synchroniczni).
- Błędy agenta: `ai.AIConfigError` daje 503, `ai.AIError` daje 502.
- Agent tworzy tylko `draft` albo `needs_clarification`. `approved` i `rejected` ustawia człowiek, decyzja jest ostateczna (409). `email_to_send` jest wypełnione tylko dla `approved`.
- Tekst z maila klienta trafia do odpowiedzi tylko przez `guard.safe_text`.
- 404 dla produktów tylko przez `get_item_or_404`. PUT podmienia wszystkie pola, PATCH tylko przesłane. Oba odświeżają `updated_at`.
- Tabele tworzy `create_all` w `lifespan`. Nie ma migracji: po zmianie schematu stary `database.db` trzeba odtworzyć (nie kasuj go bez zgody właściciela, może mieć dane).
- `pytest.ini` zamienia ostrzeżenia o przestarzałych funkcjach w błędy. Wyjątek ma tylko jedno ostrzeżenie z wnętrza `google-genai`. Nie wyciszaj innych, napraw przyczynę.
- Komentarze w kodzie po angielsku, krótkie, tylko gdy wyjaśniają „dlaczego”. Komunikaty dla użytkownika, dokumentacja i commity po polsku.
- Każda zmiana zachowania ma test.
