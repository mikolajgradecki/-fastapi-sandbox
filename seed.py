"""Fill the database with a sample IT distributor catalog: python seed.py

Uses the same database as the app (DATABASE_URL, by default database.db).
Products whose name is already in the database are skipped, so running it twice adds nothing.
"""

from sqlmodel import Session, SQLModel, select

from database import engine
from models import Item, ItemCreate, utc_now

# IT distributor catalog, net prices in PLN. A few items have stock 0 to show shortages.
PRODUCTS = [
    # Laptops
    {"name": "Laptop Dell Latitude 5450 14 i5 16GB 512GB", "price": "4299.00", "category": "laptopy", "stock": 25, "description": "Intel Core Ultra 5, Windows 11 Pro, 3 lata gwarancji"},
    {"name": "Laptop Dell Latitude 7450 14 i7 32GB 1TB", "price": "6899.00", "category": "laptopy", "stock": 8, "description": "Intel Core Ultra 7, ekran dotykowy"},
    {"name": "Laptop Lenovo ThinkPad E14 Gen 6 i5 16GB 512GB", "price": "3799.00", "category": "laptopy", "stock": 40},
    {"name": "Laptop Lenovo ThinkPad T14 Gen 5 i7 32GB 1TB", "price": "6499.00", "category": "laptopy", "stock": 0, "description": "Wysyłka po dostawie od producenta"},
    {"name": "Laptop HP ProBook 450 G11 15.6 i5 16GB 512GB", "price": "3599.00", "category": "laptopy", "stock": 32},
    {"name": "Laptop HP EliteBook 840 G11 14 i7 32GB 1TB", "price": "7499.00", "category": "laptopy", "stock": 5},
    {"name": "Laptop Apple MacBook Air 13 M3 16GB 512GB", "price": "6199.00", "category": "laptopy", "stock": 12},
    # Monitors
    {"name": "Monitor Dell P2425H 24 FHD IPS", "price": "689.00", "category": "monitory", "stock": 60},
    {"name": "Monitor Dell P2725H 27 FHD IPS", "price": "899.00", "category": "monitory", "stock": 45},
    {"name": "Monitor Dell U2724D 27 QHD IPS", "price": "1749.00", "category": "monitory", "stock": 14, "description": "USB-C, 120 Hz"},
    {"name": "Monitor Dell U3224KB 32 6K", "price": "7899.00", "category": "monitory", "stock": 2},
    {"name": "Monitor LG 24MR400 24 FHD IPS", "price": "399.00", "category": "monitory", "stock": 80},
    {"name": "Monitor LG 27UP850N 27 4K IPS", "price": "1599.00", "category": "monitory", "stock": 0},
    {"name": "Monitor iiyama ProLite XUB2493HS 24 FHD", "price": "529.00", "category": "monitory", "stock": 35, "description": "Regulacja wysokości, pivot"},
    {"name": "Monitor Samsung ViewFinity S8 27 4K", "price": "1399.00", "category": "monitory", "stock": 9},
    # Docking stations
    {"name": "Stacja dokująca Dell WD19S USB-C 130W", "price": "749.00", "category": "stacje-dokujace", "stock": 30},
    {"name": "Stacja dokująca Dell WD22TB4 Thunderbolt 4", "price": "1299.00", "category": "stacje-dokujace", "stock": 10},
    {"name": "Stacja dokująca Lenovo ThinkPad Universal USB-C", "price": "899.00", "category": "stacje-dokujace", "stock": 18},
    {"name": "Stacja dokująca HP USB-C Dock G5", "price": "829.00", "category": "stacje-dokujace", "stock": 0},
    {"name": "Stacja dokująca Unitek USB-C 8w1", "price": "239.00", "category": "stacje-dokujace", "stock": 50, "description": "HDMI, LAN, 3x USB-A, czytnik kart"},
    # Mice
    {"name": "Mysz Logitech MX Master 3S", "price": "379.00", "category": "myszy", "stock": 40},
    {"name": "Mysz Logitech M185 bezprzewodowa", "price": "49.00", "category": "myszy", "stock": 200},
    {"name": "Mysz Logitech Signature M650", "price": "129.00", "category": "myszy", "stock": 75},
    {"name": "Mysz Dell MS116 przewodowa", "price": "29.00", "category": "myszy", "stock": 150},
    {"name": "Mysz Microsoft Bluetooth Ergonomic", "price": "149.00", "category": "myszy", "stock": 0},
    # Keyboards
    {"name": "Klawiatura Logitech MX Keys S", "price": "449.00", "category": "klawiatury", "stock": 22},
    {"name": "Klawiatura Logitech K120 przewodowa", "price": "45.00", "category": "klawiatury", "stock": 180},
    {"name": "Zestaw Logitech MK295 klawiatura i mysz", "price": "119.00", "category": "klawiatury", "stock": 90, "description": "Ciche klawisze, bezprzewodowy"},
    {"name": "Klawiatura Dell KB216 przewodowa", "price": "59.00", "category": "klawiatury", "stock": 120},
    {"name": "Klawiatura mechaniczna Keychron K8 Pro", "price": "499.00", "category": "klawiatury", "stock": 6},
    # Headsets
    {"name": "Słuchawki Jabra Evolve2 65 Flex", "price": "899.00", "category": "sluchawki", "stock": 20, "description": "Certyfikat Microsoft Teams"},
    {"name": "Słuchawki Jabra Evolve2 30 SE USB-C", "price": "299.00", "category": "sluchawki", "stock": 65},
    {"name": "Słuchawki Logitech Zone Vibe 100", "price": "379.00", "category": "sluchawki", "stock": 15},
    {"name": "Słuchawki Poly Voyager Focus 2", "price": "1199.00", "category": "sluchawki", "stock": 4},
    {"name": "Słuchawki Sony WH-1000XM5", "price": "1299.00", "category": "sluchawki", "stock": 0},
    # Cables
    {"name": "Kabel HDMI 2.1 2m", "price": "39.00", "category": "kable", "stock": 300},
    {"name": "Kabel DisplayPort 1.4 2m", "price": "45.00", "category": "kable", "stock": 220},
    {"name": "Kabel USB-C do USB-C 100W 1m", "price": "29.00", "category": "kable", "stock": 400},
    {"name": "Kabel sieciowy RJ45 Cat6 3m", "price": "12.00", "category": "kable", "stock": 500},
    {"name": "Adapter USB-C do HDMI 4K", "price": "69.00", "category": "kable", "stock": 140},
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
