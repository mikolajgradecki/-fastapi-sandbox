# FastAPI sandbox: agent ofertowy B2B

API w FastAPI i SQLModel z katalogiem produktów dystrybutora IT (`/items`) i agentem AI, który zamienia maila z zapytaniem w ofertę (`/offers`). Dane trzyma baza SQLite w pliku `database.db`, a agent korzysta z Anthropic API (Claude) albo Google Gemini API, do wyboru w `.env`.

## Problem biznesowy i jak go rozwiązuje

Dystrybutor sprzętu IT dostaje codziennie maile z zapytaniami ofertowymi, a handlowiec ręcznie szuka produktów w katalogu, sprawdza stany i przepisuje ceny do odpowiedzi. Agent czyta maila, wypisuje z niego pozycje, ilości i budżety, a potem sam przeszukuje katalog i dobiera produkty albo zamienniki. Każdy wybór modelu przechodzi walidację w zwykłym kodzie: produkt musi istnieć, cena zawsze pochodzi z bazy, a ilość nie może przekroczyć stanu magazynowego, więc oferta nie zawiera zmyślonych produktów ani cen. Gdy w mailu brakuje ilości albo pozycja jest zbyt ogólna, agent nie zgaduje, tylko zadaje klientowi pytania. Podejrzane fragmenty maila (prośby o rabat, polecenia dla AI) oznacza flagą do sprawdzenia. Handlowiec dostaje szkic oferty z sumą netto, listą braków i szkicem maila. Mail jest gotowy do wysyłki dopiero wtedy, gdy handlowiec zatwierdzi ofertę.

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

### 3. Klucz API modelu

Skopiuj `.env.example` do pliku `.env`, wybierz dostawcę i wpisz klucz:

```powershell
Copy-Item .env.example .env
notepad .env
```

| Zmienna | Znaczenie |
|---|---|
| `LLM_PROVIDER` | `anthropic` albo `gemini` (domyślnie `gemini`) |
| `ANTHROPIC_API_KEY` | klucz z https://platform.claude.com, może też być zmienną systemową |
| `ANTHROPIC_MODEL` | domyślnie `claude-haiku-5-5` |
| `GEMINI_API_KEY` | klucz z https://aistudio.google.com/apikey |
| `GEMINI_MODEL` | domyślnie `gemini-3.8-flash` |

Plik `.env` jest w `.gitignore`, więc klucz nie trafi do repozytorium. Aplikacja nigdzie nie wypisuje klucza, także w komunikatach błędów. Bez klucza katalog działa normalnie, a tylko `/offers/from-email` odpowiada kodem 503. Serwer czyta `.env` przy starcie, więc po zmianie tego pliku uruchom go ponownie.

### 4. Serwer

```powershell
python -m uvicorn main:app --reload
```

Serwer działa pod adresem http://127.0.0.1:8000. Opcja `--reload` restartuje go po każdej zmianie w kodzie. Zatrzymujesz go klawiszami `Ctrl+C`.

### 5. Dokumentacja i testowanie w przeglądarce

Otwórz http://127.0.0.1:8000/docs. Każdy endpoint możesz tam wypróbować przyciskiem „Try it out”.

### 6. Testy

```powershell
python -m pytest
```

Testy używają osobnej bazy w pamięci, więc nie zmieniają pliku `database.db`. Gemini i Anthropic są w nich zastąpione fałszywymi klientami, więc testy nie potrzebują klucza ani internetu.

## Baza danych

Adres bazy pochodzi ze zmiennej środowiskowej `DATABASE_URL`. Domyślnie to `sqlite:///database.db`. Na przykład:

```powershell
$env:DATABASE_URL = "sqlite:///inna-baza.db"
python -m uvicorn main:app --reload
```

Tabele powstają przy starcie serwera. Projekt nie ma migracji, więc po zmianie pól w modelach usuń `database.db`. Serwer założy go od nowa, ale dane z pliku przepadną. Przed usunięciem zatrzymaj serwer, bo Windows nie pozwoli usunąć otwartego pliku.

### Przykładowe dane

```powershell
python seed.py
```

Skrypt dodaje katalog dystrybutora IT: 40 produktów w 7 kategoriach (`laptopy`, `monitory`, `stacje-dokujace`, `myszy`, `klawiatury`, `sluchawki`, `kable`), z cenami netto i stanami magazynowymi. Kilka produktów ma stan 0, żeby było widać braki w ofertach. Dane trafiają do tej samej bazy, której używa serwer. Produktów, które już są w bazie, nie dodaje drugi raz, więc możesz go uruchamiać wielokrotnie.

## Endpointy

Pole `id` nadaje baza. Pola `created_at` i `updated_at` ustawia serwer, w UTC. Klient ich nie wysyła.

Kwoty są typu Decimal, a w JSON przychodzą jako tekst, np. `"899.00"`. Dzięki temu nie gubią groszy na zaokrągleniach. Wysyłać możesz je jako liczbę albo tekst.

Zasady walidacji produktu:
- `name`: od 1 do 100 znaków.
- `price`: większe od 0, najwyżej 2 miejsca po przecinku.
- `category`: od 1 do 50 znaków, zapisywana małymi literami, domyślnie `inne`.
- `stock`: 0 lub więcej, domyślnie 0.
- `description`: opcjonalne.

Gdy dane nie przejdą walidacji, serwer odpowiada kodem 422.

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

Dodaje produkt.

Żądanie:

```json
{
  "name": "Monitor Dell P2725H 27 FHD IPS",
  "price": 899,
  "category": "Monitory",
  "stock": 45,
  "description": "Regulacja wysokości"
}
```

Odpowiedź `201`:

```json
{
  "name": "Monitor Dell P2725H 27 FHD IPS",
  "price": "899.00",
  "description": "Regulacja wysokości",
  "category": "monitory",
  "stock": 45,
  "id": 1,
  "created_at": "2026-10-13T16:59:56.532352Z",
  "updated_at": "2026-10-13T16:59:56.532352Z"
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
      "ctx": {"gt": 0}
    }
  ]
}
```

### GET /items

Zwraca listę produktów posortowaną po `id`. Parametry w adresie są opcjonalne:

| Parametr | Domyślnie | Znaczenie |
|---|---|---|
| `offset` | 0 | Ile produktów pominąć od początku |
| `limit` | 20 | Ile produktów zwrócić, od 1 do 100 |
| `name` | brak | Słowa z nazwy, każde musi wystąpić, bez rozróżniania wielkości liter |
| `category` | brak | Kategoria, np. `monitory` |
| `min_price` | brak | Najniższa cena, włącznie |
| `max_price` | brak | Najwyższa cena, włącznie |

Przykład: `GET /items?category=monitory&name=dell 27&max_price=1000`

Odpowiedź `200`:

```json
[
  {
    "name": "Monitor Dell P2725H 27 FHD IPS",
    "price": "899.00",
    "description": "Regulacja wysokości",
    "category": "monitory",
    "stock": 45,
    "id": 1,
    "created_at": "2026-10-13T16:59:56.532352Z",
    "updated_at": "2026-10-13T16:59:56.532352Z"
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

Zwraca jeden produkt, np. `GET /items/1`, w tym samym kształcie co `POST /items`.

Odpowiedź `404`, gdy produktu nie ma. Ten sam kod i tę samą treść zwracają PUT, PATCH i DELETE:

```json
{
  "detail": "Item not found"
}
```

### PUT /items/{item_id}

Podmienia cały produkt. Pole, którego nie wyślesz, wraca do wartości domyślnej: `description` do `null`, `category` do `inne`, `stock` do 0.

Żądanie `PUT /items/1`:

```json
{
  "name": "Monitor Dell P2725H 27 FHD IPS",
  "price": "849.00",
  "category": "monitory"
}
```

Odpowiedź `200`:

```json
{
  "name": "Monitor Dell P2725H 27 FHD IPS",
  "price": "849.00",
  "description": null,
  "category": "monitory",
  "stock": 0,
  "id": 1,
  "created_at": "2026-10-13T16:59:56.532352Z",
  "updated_at": "2026-10-13T16:59:56.552083Z"
}
```

### PATCH /items/{item_id}

Zmienia tylko pola, które wyślesz. Pozostałe zostają bez zmian. `"description": null` czyści opis. `null` dla `name`, `price`, `category` albo `stock` daje 422.

Żądanie `PATCH /items/1`:

```json
{
  "stock": 30
}
```

Odpowiedź `200`:

```json
{
  "name": "Monitor Dell P2725H 27 FHD IPS",
  "price": "849.00",
  "description": null,
  "category": "monitory",
  "stock": 30,
  "id": 1,
  "created_at": "2026-10-13T16:59:56.532352Z",
  "updated_at": "2026-10-13T16:59:56.559057Z"
}
```

### DELETE /items/{item_id}

Usuwa produkt, np. `DELETE /items/1`. Odpowiedź `204` nie ma treści.

## Agent ofertowy

Agent działa w czterech krokach:

1. **Ekstrakcja** (`ai.py`): model ze structured output zamienia maila na listę pozycji z opisem, ilością i opcjonalnym budżetem, plus termin, uwagi, pytania do klienta i flagi. Pozycja bez ilości albo zbyt ogólna („jakiś monitor”) nie jest zgadywana.
2. **Dobór** (`ai.py`): model wywołuje narzędzia `search_items` i `get_item`, które korzystają z tej samej logiki co `GET /items`. Na koniec przekazuje wybór przez `submit_selection`. Do doboru trafiają tylko jasne pozycje.
3. **Walidacja** (`offers.py`): zwykły kod, bez AI. Produkt musi istnieć, cena zawsze pochodzi z bazy, ilość nie może przekroczyć stanu magazynowego. Pozycje, które nie przejdą, trafiają do `missing` z powodem. Szkic maila powstaje z szablonu, tylko z danych po walidacji.
4. **Decyzja człowieka**: oferta zapisuje się jako szkic. Handlowiec ją zatwierdza (`/approve`) albo odrzuca z powodem (`/reject`). Dopiero zatwierdzona oferta ma wypełnione `email_to_send`.

Oba modele (Claude i Gemini) przechodzą tę samą ścieżkę: te same instrukcje, te same narzędzia i ta sama walidacja. Dostawcę wybiera `LLM_PROVIDER`.

### Ochrona przed prompt injection

Mail klienta to dane, nie polecenia. Model dostaje go w bloku `<email_klienta>`, z którego wycinane są podrobione znaczniki. Nawet gdy model da się przekonać do „rabatu 90%”, nic się nie zmienia: ceny i tak pochodzą z bazy, a szkic maila powstaje z szablonu. Fragmenty maila, które wyglądają na prośbę o rabat, darmowy towar albo polecenie dla AI, trafiają do `flags` (wykrywa je model i niezależnie od niego wyrażenia regularne w `guard.py`). Takie fragmenty nie trafiają też do treści odpowiedzi.

### POST /offers/from-email

Żądanie:

```json
{
  "email_text": "Dzień dobry, prosimy o ofertę: ..."
}
```

Odpowiedź `201`, przykład dla pierwszego maila z sekcji niżej. W bazie z `seed.py` monitor 27 cali 4K ma stan 0, więc trafia do braków:

```json
{
  "id": 1,
  "status": "draft",
  "availability": "partial",
  "total": "25240.00",
  "lines": [
    {
      "item_id": 2,
      "item_name": "Laptop Dell Latitude 5450 14 i5 16GB 512GB",
      "requested": "laptop 14 cali 16 GB RAM",
      "quantity": 5,
      "unit_price": "4299.00",
      "line_total": "21495.00",
      "is_substitute": false,
      "note": null
    },
    {
      "item_id": 16,
      "item_name": "Stacja dokująca Dell WD19S USB-C 130W",
      "requested": "stacja dokująca USB-C",
      "quantity": 5,
      "unit_price": "749.00",
      "line_total": "3745.00",
      "is_substitute": false,
      "note": null
    }
  ],
  "missing": [
    {
      "requested": "monitor 27 cali 4K",
      "quantity": 3,
      "reason": "Monitor LG 27UP850N 27 4K IPS: na stanie 0 szt., zapytanie o 3 szt."
    }
  ],
  "flags": [],
  "clarifying_questions": [],
  "reply_draft": "Dzień dobry,\n\ndziękujemy za zapytanie.\nPrzesyłamy ofertę (ceny netto):\n\n1. Laptop Dell Latitude 5450 14 i5 16GB 512GB: 5 szt. x 4 299,00 zł = 21 495,00 zł\n2. Stacja dokująca Dell WD19S USB-C 130W: 5 szt. x 749,00 zł = 3 745,00 zł\n\nRazem netto: 25 240,00 zł.\n\nObecnie nie możemy zaoferować:\n- monitor 27 cali 4K (3 szt.)\nChętnie zaproponujemy inne rozwiązanie.\n\nTermin dostawy (30 października) potwierdzimy po złożeniu zamówienia.\n\nOferta jest ważna 14 dni.\n\nPozdrawiamy,\nDział sprzedaży",
  "email_to_send": null,
  "rejection_reason": null,
  "created_at": "2026-10-13T16:59:56.583295Z",
  "decided_at": null
}
```

Pola:
- `status`: `draft` (czeka na handlowca), `needs_clarification` (szkic zawiera pytania do klienta), `approved` albo `rejected`. Agent tworzy tylko pierwsze dwa.
- `availability`: `complete` (wszystko w ofercie), `partial` (część pozycji brakuje) albo `unavailable` (nic nie da się zaoferować).
- `flags`: podejrzane fragmenty maila do sprawdzenia przez człowieka.
- `clarifying_questions`: pytania do klienta. Pozycje, których dotyczą, nie są wyceniane.
- `email_to_send`: treść do wysłania, tylko po zatwierdzeniu. Wcześniej `null`.

Przy zamienniku `is_substitute` ma wartość `true`, a `note` opisuje różnicę. Produkt droższy niż budżet klienta zostaje w ofercie z notatką „Powyżej budżetu klienta”.

Błędy:
- `422`: pusty `email_text` albo dłuższy niż 20 000 znaków.
- `502`: API modelu zwróciło błąd (np. brak środków na koncie) albo odpowiedź, której nie da się użyć. Treść błędu jest w `detail`.
- `503`: brak klucza wybranego dostawcy albo nieznany `LLM_PROVIDER`.

### GET /offers/{offer_id}

Zwraca zapisaną ofertę w tym samym kształcie co `POST /offers/from-email`. Gdy oferty nie ma, odpowiada `404` z `{"detail": "Offer not found"}`.

### POST /offers/{offer_id}/approve

Bez treści żądania. Zmienia status na `approved`, ustawia `decided_at` i wypełnia `email_to_send` treścią `reply_draft`. Zatwierdzić można ofertę w statusie `draft` albo `needs_clarification` (wtedy klient dostaje pytania).

### POST /offers/{offer_id}/reject

```json
{
  "reason": "Klient ma umowę ramową z innym cennikiem."
}
```

Zmienia status na `rejected` i zapisuje powód w `rejection_reason`. `email_to_send` zostaje `null`. Powód jest obowiązkowy (3 do 500 znaków), bez niego odpowiedź to `422`.

Decyzja jest ostateczna: druga próba zatwierdzenia albo odrzucenia daje `409` z `{"detail": "Oferta ma już status approved."}`. Nieistniejąca oferta daje `404`.

### Przykładowe maile do testów w /docs

Uruchom najpierw `python seed.py`. Potem w `/docs` otwórz `POST /offers/from-email`, kliknij „Try it out” i wklej jedno z żądań.

Mail 1: kilka pozycji, budżet i jeden brak towaru:

```json
{
  "email_text": "Dzień dobry, prosimy o ofertę: 5 laptopów 14 cali z 16 GB RAM do 4500 zł netto, 5 stacji dokujących USB-C i 3 monitory 27 cali 4K. Dostawa do 30 października. Pozdrawiam, Anna Nowak"
}
```

Mail 2: wyposażenie stanowisk z akcesoriami i budżetem:

```json
{
  "email_text": "Witam, otwieramy nowe biuro i potrzebujemy 12 zestawów: monitor 24 cale, klawiatura z myszką bezprzewodowa i słuchawki do Teams. Do tego 12 kabli HDMI 2 m. Budżet na monitor to maksymalnie 600 zł netto za sztukę. Czy dacie radę dostarczyć w ciągu 2 tygodni? Tomasz Wiśniewski, IT Manager"
}
```

## Evale

Testy w `tests/` sprawdzają kod z fałszywym modelem. Evale sprawdzają prawdziwy model: wysyłają 8 maili z `evals/cases.json` przez API i porównują ofertę z oczekiwanym wynikiem.

```powershell
python run_evals.py
python run_evals.py brak
```

Drugi wariant uruchamia tylko przypadki, których nazwa zawiera podany tekst. Skrypt używa dostawcy i klucza z `.env`, więc każde uruchomienie kosztuje kilka wywołań API. Katalog to świeża baza w pamięci z `seed.py`, więc `database.db` zostaje nietknięty. Przy limicie zapytań (429) albo przeciążeniu serwera skrypt ponawia próbę do 3 razy.

Przypadki: zwykłe zapytanie, literówki, za mały budżet, brak towaru na stanie, niejasne zapytanie, prompt injection, mail po angielsku i 8 pozycji naraz. W każdym skrypt sprawdza też reguły wspólne: cena równa cenie z katalogu, ilość nie większa niż stan, brak `email_to_send` przed zatwierdzeniem i poprawne `email_to_send` po zatwierdzeniu.

Wynik wygląda tak:

```
Evale: 8 przypadków, dostawca anthropic, model claude-haiku-5-5

[OK]   1. zwykle zapytanie (5.2 s)
...
[BŁĄD] 4. brak na stanie (12.4 s)
       - zaoferowano produkt bez stanu: LG 27UP850N

Wynik: 7/8
```

Kod wyjścia to 0, gdy przechodzą wszystkie przypadki, i 1 w przeciwnym razie.
