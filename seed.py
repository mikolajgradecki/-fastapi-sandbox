"""Fill the database with sample products: python seed.py

Uses the same database as the app (DATABASE_URL, by default database.db).
Products whose name is already in the database are skipped, so running it twice adds nothing.
"""

from sqlmodel import Session, SQLModel, select

from main import Item, ItemCreate, engine, utc_now

PRODUCTS = [
    # Electronics
    {"name": "Laptop Lenovo ThinkPad T14", "price": 5499.0, "description": "14 cali, 16 GB RAM, 512 GB SSD"},
    {"name": "Smartfon Samsung Galaxy S25", "price": 3899.0, "description": "256 GB, czarny"},
    {"name": "Słuchawki Sony WH-1000XM6", "price": 1599.0, "description": "Bezprzewodowe, z redukcją szumów"},
    {"name": "Monitor Dell 27 4K", "price": 1899.99},
    {"name": "Myszka Logitech MX Master 3S", "price": 449.0, "description": "Cicha, ergonomiczna"},
    {"name": "Klawiatura mechaniczna Keychron K2", "price": 399.0},
    {"name": "Kabel USB-C 1 m", "price": 19.99},
    {"name": "Powerbank Anker 20000 mAh", "price": 179.0, "description": "Szybkie ładowanie 30 W"},
    {"name": "Telewizor LG OLED 65", "price": 7999.0, "description": "65 cali, 120 Hz"},
    {"name": "Karta pamięci microSD 128 GB", "price": 59.9},
    {"name": "Konsola PlayStation 5", "price": 2499.0},
    # Books
    {"name": "Wiedźmin: Ostatnie życzenie", "price": 39.9, "description": "Andrzej Sapkowski"},
    {"name": "Lalka", "price": 24.99, "description": "Bolesław Prus, wydanie szkolne"},
    {"name": "Czysty kod", "price": 89.0, "description": "Robert C. Martin"},
    {"name": "Python. Wprowadzenie", "price": 149.0},
    {"name": "Solaris", "price": 34.9},
    {"name": "Atlas świata dla dzieci", "price": 69.0, "description": "Twarda oprawa, 120 stron"},
    {"name": "Zakładka do książki", "price": 5.0},
    {"name": "Pan Tadeusz", "price": 19.9, "description": "Adam Mickiewicz"},
    {"name": "Sztuka wojny", "price": 29.99},
    # Sport
    {"name": "Rower górski Kross Hexagon", "price": 2299.0, "description": "Rama 19 cali, koła 29"},
    {"name": "Hantle 2 x 10 kg", "price": 249.0},
    {"name": "Mata do jogi", "price": 79.99, "description": "6 mm, antypoślizgowa"},
    {"name": "Piłka nożna Adidas", "price": 129.0, "description": "Rozmiar 5"},
    {"name": "Buty do biegania Asics Gel-Nimbus", "price": 699.0},
    {"name": "Bidon 750 ml", "price": 25.0},
    {"name": "Rakieta tenisowa Wilson", "price": 549.0, "description": "Dla średnio zaawansowanych"},
    {"name": "Skakanka", "price": 15.99},
    {"name": "Bieżnia elektryczna", "price": 3299.0, "description": "Składana, do 120 kg"},
    {"name": "Kask rowerowy", "price": 199.0},
]


def seed(session: Session) -> int:
    """Add the products that are not in the database yet and return how many were added."""
    existing = set(session.exec(select(Item.name)).all())
    added = 0
    for product in PRODUCTS:
        if product["name"] in existing:
            continue
        # ItemCreate checks the same rules as the API (name length, price > 0)
        item = ItemCreate.model_validate(product)
        now = utc_now()
        session.add(Item.model_validate(item, update={"created_at": now, "updated_at": now}))
        added += 1
    session.commit()
    return added


def main() -> None:
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        added = seed(session)
        total = len(session.exec(select(Item.id)).all())
    print(f"Dodano produktów: {added}. Razem w bazie: {total}.")


if __name__ == "__main__":
    main()
