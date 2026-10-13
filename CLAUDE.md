# FastAPI sandbox

Projekt do nauki: CRUD przedmiotów (`/items`) w FastAPI + SQLModel na SQLite. Python 3.14, Windows.

## Struktura

- `main.py`: cała aplikacja (modele, engine, `get_session`, endpointy).
- `seed.py`: 30 przykładowych produktów, `python seed.py`. Pomija nazwy, które już są w bazie.
- `tests/test_main.py`: wszystkie testy. Fixture `test_db` (autouse) podmienia `get_session` na bazę w pamięci przez `app.dependency_overrides`.
- `README.md`: instrukcja po polsku dla ludzi i przykłady JSON. Przy zmianie API zaktualizuj przykłady.
- `.github/workflows/tests.yml`: CI, `pytest` na Python 3.14.

## Komendy

- Testy: `python -m pytest` (`pytest.exe` nie jest w PATH).
- Serwer: `python -m uvicorn main:app --reload`, dokumentacja na http://127.0.0.1:8000/docs.
- Zależności: `requirements.txt` (aplikacja), `requirements-dev.txt` (+ pytest, httpx2). Wersje przypięte przez `==`.

## Modele

- `ItemBase`: `name` (1-100 znaków), `price` (> 0), `description` (opcjonalne).
- `Item` (tabela): + `id`, `created_at`, `updated_at` (UTC, ustawia serwer).
- `ItemCreate` (POST, PUT), `ItemUpdate` (PATCH, wszystko opcjonalne, `null` dla `name` i `price` daje 422), `ItemPublic` (`response_model` każdego endpointu `/items`).

## Konwencje

- Endpointy używające sesji to `def`, nie `async def` (sesja SQLModel jest synchroniczna).
- 404 tylko przez `get_item_or_404`. PUT podmienia wszystkie pola (`model_dump()`), PATCH tylko przesłane (`exclude_unset=True`). Oba odświeżają `updated_at`.
- Baza: `DATABASE_URL`, domyślnie `sqlite:///database.db`. Tabele tworzy `create_all` w `lifespan`. Nie ma migracji: po zmianie schematu stary `database.db` trzeba odtworzyć (nie kasuj go bez zgody właściciela, może mieć dane).
- `database.db` jest w `.gitignore`. Testy go nie dotykają (`TestClient` bez `with` nie uruchamia `lifespan`).
- `pytest.ini` zamienia ostrzeżenia o przestarzałych funkcjach w błędy. Nie wyciszaj ich, napraw przyczynę.
- Komentarze w kodzie po angielsku, krótkie, tylko gdy wyjaśniają „dlaczego”. Dokumentacja i commity po polsku.
- Każda zmiana zachowania ma test. Nowe testy dopisuj w `tests/test_main.py`.
