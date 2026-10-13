# FastAPI sandbox

Proste API do zarządzania przedmiotami (`/items`) w FastAPI i SQLModel. Dane trzyma baza SQLite w pliku `database.db`.

## Uruchomienie na Windows

Potrzebujesz Pythona 3.14. Wszystkie komendy wpisujesz w PowerShellu w katalogu projektu.

### 1. Środowisko wirtualne (.venv)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Po aktywacji na początku linii zobaczysz `(.venv)`. Gdy PowerShell zablokuje skrypt komunikatem o „execution policy”, wpisz raz:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

W zwykłym wierszu poleceń (cmd) aktywujesz środowisko komendą `.venv\Scripts\activate.bat`.

### 2. Zależności

```powershell
python -m pip install -r requirements-dev.txt
```

`requirements.txt` zawiera to, czego potrzebuje sama aplikacja. `requirements-dev.txt` dokłada do tego pytest i httpx2 do testów.

### 3. Serwer

```powershell
python -m uvicorn main:app --reload
```

Serwer działa pod adresem http://127.0.0.1:8000. Opcja `--reload` restartuje go po każdej zmianie w kodzie. Zatrzymujesz go klawiszami `Ctrl+C`.

### 4. Dokumentacja i testowanie w przeglądarce

Otwórz http://127.0.0.1:8000/docs. Każdy endpoint możesz tam wypróbować przyciskiem „Try it out”.

### 5. Testy

```powershell
python -m pytest
```

Testy używają osobnej bazy w pamięci, więc nie zmieniają pliku `database.db`.

## Baza danych

Adres bazy pochodzi ze zmiennej środowiskowej `DATABASE_URL`. Domyślnie to `sqlite:///database.db`. Na przykład:

```powershell
$env:DATABASE_URL = "sqlite:///inna-baza.db"
python -m uvicorn main:app --reload
```

Tabele powstają przy starcie serwera. Projekt nie ma migracji, więc po zmianie pól w modelu `Item` usuń `database.db`. Serwer założy go od nowa, ale dane z pliku przepadną. Przed usunięciem zatrzymaj serwer, bo Windows nie pozwoli usunąć otwartego pliku.

### Przykładowe dane

```powershell
python seed.py
```

Skrypt dodaje 30 produktów (elektronika, książki, sport) do tej samej bazy, której używa serwer. Produktów, które już są w bazie, nie dodaje drugi raz, więc możesz go uruchamiać wielokrotnie.

## Endpointy

Pole `id` nadaje baza. Pola `created_at` i `updated_at` ustawia serwer, w UTC. Klient ich nie wysyła.

Zasady walidacji: `name` musi mieć od 1 do 100 znaków, `price` musi być większe od 0, `description` jest opcjonalne. Gdy dane nie przejdą walidacji, serwer odpowiada kodem 422.

### GET /health

Sprawdza, czy działa serwer i baza.

Odpowiedź `200`:

```json
{
  "status": "ok",
  "database": "ok"
}
```

Odpowiedź `503`, gdy baza nie odpowiada:

```json
{
  "status": "error",
  "database": "unavailable"
}
```

### POST /items

Dodaje przedmiot.

Żądanie:

```json
{
  "name": "Laptop",
  "price": 3999.99,
  "description": "16 GB RAM"
}
```

Odpowiedź `201`:

```json
{
  "name": "Laptop",
  "price": 3999.99,
  "description": "16 GB RAM",
  "id": 1,
  "created_at": "2026-10-13T16:36:57.531860Z",
  "updated_at": "2026-10-13T16:36:57.531860Z"
}
```

Odpowiedź `422` na przykład dla `"price": -5`:

```json
{
  "detail": [
    {
      "type": "greater_than",
      "loc": ["body", "price"],
      "msg": "Input should be greater than 0",
      "input": -5,
      "ctx": {"gt": 0.0}
    }
  ]
}
```

### GET /items

Zwraca listę przedmiotów posortowaną po `id`. Parametry w adresie są opcjonalne:

| Parametr | Domyślnie | Znaczenie |
|---|---|---|
| `offset` | 0 | Ile przedmiotów pominąć od początku |
| `limit` | 20 | Ile przedmiotów zwrócić, od 1 do 100 |
| `name` | brak | Fragment nazwy, bez rozróżniania wielkości liter |
| `min_price` | brak | Najniższa cena, włącznie |
| `max_price` | brak | Najwyższa cena, włącznie |

Przykład: `GET /items?name=lap&max_price=5000&limit=10`

Odpowiedź `200`:

```json
[
  {
    "name": "Laptop",
    "price": 3999.99,
    "description": "16 GB RAM",
    "id": 1,
    "created_at": "2026-10-13T16:36:57.531860Z",
    "updated_at": "2026-10-13T16:36:57.531860Z"
  }
]
```

Odpowiedź `422`, gdy `min_price` jest większe niż `max_price`:

```json
{
  "detail": "min_price cannot be greater than max_price"
}
```

### GET /items/{item_id}

Zwraca jeden przedmiot, np. `GET /items/1`.

Odpowiedź `200`:

```json
{
  "name": "Laptop",
  "price": 3999.99,
  "description": "16 GB RAM",
  "id": 1,
  "created_at": "2026-10-13T16:36:57.531860Z",
  "updated_at": "2026-10-13T16:36:57.531860Z"
}
```

Odpowiedź `404`, gdy przedmiotu nie ma. Ten sam kod i tę samą treść zwracają PUT, PATCH i DELETE:

```json
{
  "detail": "Item not found"
}
```

### PUT /items/{item_id}

Podmienia cały przedmiot. Pole, którego nie wyślesz, wraca do wartości domyślnej, np. `description` zmieni się na `null`.

Żądanie `PUT /items/1`:

```json
{
  "name": "Laptop Pro",
  "price": 5499.0
}
```

Odpowiedź `200`:

```json
{
  "name": "Laptop Pro",
  "price": 5499.0,
  "description": null,
  "id": 1,
  "created_at": "2026-10-13T16:36:57.531860Z",
  "updated_at": "2026-10-13T16:36:57.544933Z"
}
```

### PATCH /items/{item_id}

Zmienia tylko pola, które wyślesz. Pozostałe zostają bez zmian. `"description": null` czyści opis. `null` dla `name` albo `price` daje 422.

Żądanie `PATCH /items/1`:

```json
{
  "description": "32 GB RAM"
}
```

Odpowiedź `200`:

```json
{
  "name": "Laptop Pro",
  "price": 5499.0,
  "description": "32 GB RAM",
  "id": 1,
  "created_at": "2026-10-13T16:36:57.531860Z",
  "updated_at": "2026-10-13T16:36:57.547495Z"
}
```

### DELETE /items/{item_id}

Usuwa przedmiot, np. `DELETE /items/1`. Odpowiedź `204` nie ma treści.
