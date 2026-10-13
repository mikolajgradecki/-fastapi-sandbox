# FastAPI sandbox: agent ofertowy B2B

Projekt do nauki: katalog produktów dystrybutora IT (`/items`) i agent Gemini, który zamienia maila z zapytaniem w ofertę (`/offers`). FastAPI + SQLModel na SQLite, Python 3.14, Windows.

## Struktura

- `main.py`: same endpointy i zależność `ai_client` (testy ją podmieniają).
- `database.py`: `DATABASE_URL`, `engine`, `get_session`, `SessionDep`.
- `models.py`: tabele `Item`, `Offer`, `OfferLine`, schematy API, typ `Money` (Decimal zapisywany w groszach jako Integer).
- `catalog.py`: `search_items`, `list_categories`, `get_item_or_404`. Wspólne dla `GET /items` i narzędzi agenta.
- `ai.py`: Gemini (`google-genai`). Krok 1 `extract_request` (structured output, `RequestSpec`), krok 2 `select_products` (własna pętla tool calling, kończy się `submit_selection`).
- `offers.py`: krok 3, walidacja bez AI (`validate_selection`), zapis, szkic maila z szablonu (`render_reply`).
- `seed.py`: 40 produktów IT w 7 kategoriach, `python seed.py`. Pomija nazwy, które już są w bazie.
- `tests/conftest.py`: fixture `test_db` (autouse) podmienia `get_session` na bazę w pamięci, `db_engine` daje do niej dostęp.
- `tests/test_main.py`: katalog i seed. `tests/test_offers.py`: agent z `FakeGemini`, który odtwarza przygotowane odpowiedzi z prawdziwych typów SDK.
- `README.md`: instrukcja po polsku i przykłady JSON. Przy zmianie API zaktualizuj przykłady.

## Komendy

- Testy: `python -m pytest` (`pytest.exe` nie jest w PATH). Nie wymagają klucza ani sieci.
- Serwer: `python -m uvicorn main:app --reload`, dokumentacja na http://127.0.0.1:8000/docs.
- Zależności: `requirements.txt` (aplikacja), `requirements-dev.txt` (+ pytest, httpx2). Wersje przypięte przez `==`.
- Klucz: `GEMINI_API_KEY` w `.env` (wzór `.env.example`, `.env` jest w `.gitignore`). Model: `GEMINI_MODEL`, domyślnie `gemini-3.8-flash`.

## Konwencje

- Kwoty to `Decimal` (`price`, `total`, `unit_price`), w JSON jako tekst `"899.00"`. Nigdy `float` w obliczeniach.
- Model AI niczego nie ustala sam: id produktu, cenę i stan zawsze sprawdza `offers.validate_selection` w bazie. Szkic maila powstaje tylko z danych po walidacji.
- Endpointy używające sesji to `def`, nie `async def` (sesja SQLModel i klient Gemini są synchroniczne).
- Błędy agenta: `ai.AIConfigError` daje 503, `ai.AIError` daje 502.
- 404 dla produktów tylko przez `get_item_or_404`. PUT podmienia wszystkie pola, PATCH tylko przesłane. Oba odświeżają `updated_at`.
- Tabele tworzy `create_all` w `lifespan`. Nie ma migracji: po zmianie schematu stary `database.db` trzeba odtworzyć (nie kasuj go bez zgody właściciela, może mieć dane).
- `pytest.ini` zamienia ostrzeżenia o przestarzałych funkcjach w błędy. Wyjątek ma tylko jedno ostrzeżenie z wnętrza `google-genai`. Nie wyciszaj innych, napraw przyczynę.
- Komentarze w kodzie po angielsku, krótkie, tylko gdy wyjaśniają „dlaczego”. Komunikaty dla użytkownika, dokumentacja i commity po polsku.
- Każda zmiana zachowania ma test.
