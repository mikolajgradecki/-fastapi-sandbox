"""Minimal HTMX panel under /ui. Server-rendered HTML fragments, no JSON, no JS of our own."""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.templating import Jinja2Templates

import ai
import offers
from database import SessionDep
from models import Offer, OfferStatus

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
templates.env.globals["format_pln"] = offers.format_pln

STATUS_LABELS = {
    OfferStatus.draft: "Szkic",
    OfferStatus.needs_clarification: "Wymaga doprecyzowania",
    OfferStatus.approved: "Zatwierdzona",
    OfferStatus.rejected: "Odrzucona",
}

ALREADY_DECIDED = {
    OfferStatus.approved: "Ta oferta została już zatwierdzona.",
    OfferStatus.rejected: "Ta oferta została już odrzucona.",
}

logger = logging.getLogger(__name__)

MAX_EMAIL_LENGTH = 20000
MAX_REASON_LENGTH = 500


def build_router(ai_client) -> APIRouter:
    router = APIRouter(prefix="/ui")
    AIClientDep = Annotated[object, Depends(ai_client)]

    def fragment(request: Request, *, offer=None, error: str | None = None, notice: str | None = None):
        # Always 200: HTMX does not swap the response of a 4xx or 5xx
        context = {"offer": offer, "error": error, "notice": notice, "status_labels": STATUS_LABELS}
        return templates.TemplateResponse(request, "_offer_card.html", context)

    def decide(request: Request, session, offer_id: int, approve: bool, reason: str | None = None):
        offer = session.get(Offer, offer_id)
        if offer is None:
            return fragment(request, error="Nie znaleziono oferty.")
        notice = None
        try:
            offer = offers.decide(session, offer, approve, reason)
        except offers.OfferAlreadyDecided:
            notice = ALREADY_DECIDED[offer.status]
        return fragment(request, offer=offers.offer_public(session, offer), notice=notice)

    @router.get("")
    def index(request: Request):
        return templates.TemplateResponse(request, "index.html", {"max_length": MAX_EMAIL_LENGTH})

    @router.post("/offers")
    def create_offer(
        request: Request, session: SessionDep, llm: AIClientDep, email_text: Annotated[str, Form()] = ""
    ):
        if not email_text.strip():
            return fragment(request, error="Wklej treść maila z zapytaniem.")
        if len(email_text) > MAX_EMAIL_LENGTH:
            return fragment(request, error=f"Mail jest za długi (maks. {MAX_EMAIL_LENGTH} znaków).")
        try:
            offer = offers.process_email(llm, session, email_text)
        except ai.AIConfigError as error:
            # The JSON endpoint answers 503 here; the page shows a fixed text, details only in the log
            logger.error("AI config error: %s", error)
            return fragment(request, error="Brak konfiguracji modelu AI.")
        except ai.AIError as error:
            logger.error("AI error: %s", error)
            return fragment(
                request, error="Agent chwilowo nie może przygotować oferty. Spróbuj ponownie za chwilę."
            )
        return fragment(request, offer=offers.offer_public(session, offer))

    @router.post("/offers/{offer_id}/approve")
    def approve(request: Request, offer_id: int, session: SessionDep):
        return decide(request, session, offer_id, approve=True)

    @router.post("/offers/{offer_id}/reject")
    def reject(request: Request, offer_id: int, session: SessionDep, reason: Annotated[str, Form()] = ""):
        reason = reason.strip()
        if not 3 <= len(reason) <= MAX_REASON_LENGTH:
            offer = session.get(Offer, offer_id)
            if offer is None:
                return fragment(request, error="Nie znaleziono oferty.")
            message = f"Podaj powód odrzucenia (od 3 do {MAX_REASON_LENGTH} znaków)."
            return fragment(request, offer=offers.offer_public(session, offer), notice=message)
        return decide(request, session, offer_id, approve=False, reason=reason)

    return router
