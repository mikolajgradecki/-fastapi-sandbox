"""Step 3 of the offer agent: validate the model's choices and save the offer.

Plain code, no AI. Whatever the model returned, every offered line has a product that exists,
the price from the database and enough stock. Anything else becomes a missing line with a reason.
"""

from decimal import Decimal

from sqlmodel import Session, select

from ai import RequestSpec, Selection
from guard import find_suspicious, merge_flags, safe_text
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


def clarifying_questions(spec: RequestSpec) -> list[str]:
    """Questions for the customer. Never empty when a line is unclear or nothing was asked for."""
    # The model's questions go to the customer, so they get the same check as e-mail text
    questions = [q for q in (safe_text(q, max_length=200) for q in spec.clarifying_questions) if q]
    unclear = [line for line in spec.lines if not line.is_clear]
    if not spec.lines:
        return questions or ["Jakie produkty i w jakich ilościach mamy uwzględnić w ofercie?"]
    if unclear and not questions:
        for line in unclear:
            what = safe_text(line.description) or "jedna z pozycji zapytania"
            if line.quantity is None:
                questions.append(f"Ile sztuk potrzebują Państwo: {what}?")
            else:
                questions.append(f"Prosimy o doprecyzowanie (model, parametry): {what}.")
    return questions


def render_reply(
    lines: list[OfferLine], spec: RequestSpec, total: Decimal, questions: list[str] = ()
) -> str:
    """Reply e-mail built only from validated data, so it cannot contain an invented price.

    Product names and prices come from the catalog. Text that came from the e-mail
    (what the customer asked for, the deadline) goes through safe_text first.
    """
    offered = [line for line in lines if line.item_id is not None]
    missing = [line for line in lines if line.item_id is None]
    position = {id(line): number for number, line in enumerate(lines, start=1)}

    def requested(line: OfferLine) -> str:
        return safe_text(line.requested) or f"pozycja nr {position[id(line)]} z zapytania"

    parts = ["Dzień dobry,", "", "dziękujemy za zapytanie."]
    if offered:
        intro = "Przesyłamy ofertę na pozycje, które możemy już wycenić" if questions else "Przesyłamy ofertę"
        parts += [f"{intro} (ceny netto):", ""]
        for number, line in enumerate(offered, start=1):
            line_total = line.unit_price * line.quantity
            parts.append(
                f"{number}. {line.item_name}: {line.quantity} szt. x "
                f"{format_pln(line.unit_price)} = {format_pln(line_total)}"
            )
            if line.is_substitute:
                parts.append(f"   Proponujemy jako zamiennik dla: {requested(line)}.")
        parts += ["", f"Razem netto: {format_pln(total)}."]
    if missing:
        parts += ["", "Obecnie nie możemy zaoferować:"]
        parts += [f"- {requested(line)} ({line.quantity} szt.)" for line in missing]
        parts.append("Chętnie zaproponujemy inne rozwiązanie.")
    if questions:
        parts += ["", "Aby przygotować pełną ofertę, prosimy o doprecyzowanie:"]
        parts += [f"{number}. {question}" for number, question in enumerate(questions, start=1)]
    deadline = safe_text(spec.deadline, max_length=60)
    if offered and deadline:
        parts += ["", f"Termin dostawy ({deadline}) potwierdzimy po złożeniu zamówienia."]
    if offered:
        parts += ["", "Oferta jest ważna 14 dni."]
    parts += ["", "Pozdrawiamy,", "Dział sprzedaży"]
    return "\n".join(parts)


def process_email(llm, session: Session, email_text: str) -> Offer:
    """The whole agent: extraction and selection by the LLM provider, then validation and saving."""
    spec = llm.extract_request(email_text)
    questions = clarifying_questions(spec)
    # Unclear lines are not guessed: only clear ones go to product selection
    clear = spec.model_copy(update={"lines": [line for line in spec.lines if line.is_clear]})
    selection = llm.select_products(session, clear) if clear.lines else Selection(choices=[])
    return create_offer(session, email_text, clear, selection, questions)


def create_offer(
    session: Session,
    email_text: str,
    spec: RequestSpec,
    selection: Selection,
    questions: list[str] = (),
) -> Offer:
    """spec holds only the clear lines; questions cover the rest."""
    lines = validate_selection(session, spec, selection)
    total = sum(
        (line.unit_price * line.quantity for line in lines if line.item_id is not None),
        Decimal("0.00"),
    )
    offer = Offer(
        customer_email_text=email_text,
        status=OfferStatus.needs_clarification if questions else offer_status(lines),
        total=total,
        reply_draft=render_reply(lines, spec, total, questions),
        clarifying_questions=list(questions),
        # The model's flags plus the pattern check, in case an injection talked the model out of it
        flags=merge_flags(spec.flags, find_suspicious(email_text)),
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
        flags=offer.flags,
        clarifying_questions=offer.clarifying_questions,
        reply_draft=offer.reply_draft,
        created_at=offer.created_at,
    )
