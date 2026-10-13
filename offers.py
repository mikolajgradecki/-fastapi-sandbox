"""Step 3 of the offer agent: validate the model's choices and save the offer.

Plain code, no AI. Whatever the model returned, every offered line has a product that exists,
the price from the database and enough stock. Anything else becomes a missing line with a reason.
"""

from decimal import Decimal

from sqlmodel import Session, select

from ai import RequestSpec, Selection
from models import (
    Item,
    Offer,
    OfferLine,
    OfferLinePublic,
    OfferMissingPublic,
    OfferPublic,
    OfferStatus,
    to_money,
)


def validate_selection(session: Session, spec: RequestSpec, selection: Selection) -> list[OfferLine]:
    """Returns one unsaved OfferLine per requested line, in the order of the request."""
    choices = {}
    for choice in selection.choices:
        # The first choice for a line wins; choices for lines that do not exist are ignored
        if 0 <= choice.request_index < len(spec.lines):
            choices.setdefault(choice.request_index, choice)

    lines = []
    for index, requested in enumerate(spec.lines):
        line = OfferLine(requested=requested.description, quantity=requested.quantity)
        lines.append(line)
        choice = choices.get(index)

        if choice is None:
            line.note = "Agent nie dobrał produktu do tej pozycji."
            continue
        if choice.item_id is None:
            line.note = choice.note or "Brak pasującego produktu w katalogu."
            continue
        item = session.get(Item, choice.item_id)
        if item is None:
            line.note = f"Produkt o id {choice.item_id} nie istnieje w katalogu."
            continue
        if requested.quantity > item.stock:
            line.note = (
                f"{item.name}: na stanie {item.stock} szt., "
                f"zapytanie o {requested.quantity} szt."
            )
            continue

        notes = []
        if choice.is_substitute:
            notes.append(choice.note or "Zamiennik.")
        elif choice.note:
            notes.append(choice.note)
        if requested.max_unit_price is not None and item.price > to_money(requested.max_unit_price):
            notes.append(
                f"Powyżej budżetu klienta (maks. {format_pln(to_money(requested.max_unit_price))} netto)."
            )

        line.item_id = item.id
        line.item_name = item.name
        # Always the catalog price, never the price the model wrote
        line.unit_price = item.price
        line.is_substitute = choice.is_substitute
        line.note = " ".join(notes) or None
    return lines


def offer_status(lines: list[OfferLine]) -> OfferStatus:
    offered = [line for line in lines if line.item_id is not None]
    if offered and len(offered) == len(lines):
        return OfferStatus.complete
    if offered:
        return OfferStatus.partial
    return OfferStatus.unavailable


def format_pln(amount: Decimal) -> str:
    """4299.5 -> '4 299,50 zł'"""
    return f"{amount:,.2f} zł".replace(",", " ").replace(".", ",")


def render_reply(lines: list[OfferLine], spec: RequestSpec, total: Decimal) -> str:
    """Reply e-mail built only from validated data, so it cannot contain an invented price."""
    offered = [line for line in lines if line.item_id is not None]
    missing = [line for line in lines if line.item_id is None]

    parts = ["Dzień dobry,", "", "dziękujemy za zapytanie."]
    if offered:
        parts += ["Przesyłamy ofertę (ceny netto):", ""]
        for number, line in enumerate(offered, start=1):
            line_total = line.unit_price * line.quantity
            parts.append(
                f"{number}. {line.item_name}: {line.quantity} szt. x "
                f"{format_pln(line.unit_price)} = {format_pln(line_total)}"
            )
            if line.is_substitute:
                parts.append(f"   Proponujemy jako zamiennik dla: {line.requested}.")
        parts += ["", f"Razem netto: {format_pln(total)}."]
    if missing:
        parts += ["", "Obecnie nie możemy zaoferować:"]
        parts += [f"- {line.requested} ({line.quantity} szt.)" for line in missing]
        parts.append("Chętnie zaproponujemy inne rozwiązanie.")
    if offered and spec.deadline:
        parts += ["", f"Termin dostawy ({spec.deadline}) potwierdzimy po złożeniu zamówienia."]
    parts += ["", "Oferta jest ważna 14 dni.", "", "Pozdrawiamy,", "Dział sprzedaży"]
    return "\n".join(parts)


def create_offer(session: Session, email_text: str, spec: RequestSpec, selection: Selection) -> Offer:
    lines = validate_selection(session, spec, selection)
    total = sum(
        (line.unit_price * line.quantity for line in lines if line.item_id is not None),
        Decimal("0.00"),
    )
    offer = Offer(
        customer_email_text=email_text,
        status=offer_status(lines),
        total=total,
        reply_draft=render_reply(lines, spec, total),
    )
    session.add(offer)
    session.flush()  # assigns offer.id for the lines
    for line in lines:
        line.offer_id = offer.id
        session.add(line)
    session.commit()
    session.refresh(offer)
    return offer


def offer_public(session: Session, offer: Offer) -> OfferPublic:
    lines = session.exec(
        select(OfferLine).where(OfferLine.offer_id == offer.id).order_by(OfferLine.id)
    ).all()
    return OfferPublic(
        id=offer.id,
        status=offer.status,
        total=offer.total,
        lines=[
            OfferLinePublic(
                item_id=line.item_id,
                item_name=line.item_name,
                requested=line.requested,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.unit_price * line.quantity,
                is_substitute=line.is_substitute,
                note=line.note,
            )
            for line in lines
            if line.item_id is not None
        ],
        missing=[
            OfferMissingPublic(requested=line.requested, quantity=line.quantity, reason=line.note)
            for line in lines
            if line.item_id is None
        ],
        reply_draft=offer.reply_draft,
        created_at=offer.created_at,
    )
