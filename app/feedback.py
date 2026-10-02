# -*- coding: utf-8 -*-
"""
Feedback aus der Oberfläche: geht per Mail an die Superadmins (ADMIN_EMAILS), Antwort an den Absender.

Möglich nur mit Anmeldung (sonst gibt es weder Absender noch Superadmins) und eingerichtetem Mailversand.
Gespeichert wird nichts; je Benutzer höchstens eine Nachricht pro COOLDOWN Sekunden.
"""
import html
import logging
import smtplib
import threading
import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import auth, mail, tenancy

log = logging.getLogger("pdf2einsatz")

router = APIRouter()
access = auth.access

COOLDOWN = 30
_lock = threading.Lock()
_last_sent = {}     # Adresse → Zeitpunkt der letzten Nachricht


def enabled():
    return bool(tenancy.ADMIN_EMAILS) and mail.enabled()


class FeedbackIn(BaseModel):
    message: str = Field(min_length=1, max_length=5000)
    view: str = Field(default="", max_length=100)       # Ansicht, aus der das Feedback kommt


@router.post("/api/feedback")
def api_feedback(feedback: FeedbackIn, a: tenancy.Access = Depends(access)):
    message = feedback.message.strip()
    if not message:
        raise HTTPException(422, "Bitte eine Nachricht eingeben.")
    if not enabled() or not a.email:
        raise HTTPException(503, "Feedback ist auf diesem Server nicht eingerichtet.")
    with _lock:
        if time.time() - _last_sent.get(a.email, 0) < COOLDOWN:
            raise HTTPException(429, "Bitte einen Moment warten, bevor du erneut Feedback sendest.")
        _last_sent[a.email] = time.time()
    scope = a.vgs.get(a.vg) if a.vg else a.selected.name if a.selected else "–"
    details = [("Von", a.email), ("Auswahl", scope), ("Ansicht", feedback.view or "–")]
    text = "\n".join(f"{k}: {v}" for k, v in details) + f"\n\n{message}\n"
    body = ("<table>" + "".join(f"<tr><th align=\"left\">{k}</th><td>{html.escape(v)}</td></tr>" for k, v in details)
            + f"</table><p style=\"white-space: pre-wrap\">{html.escape(message)}</p>")
    try:
        for recipient in sorted(tenancy.ADMIN_EMAILS):
            mail.send(recipient, f"Feedback Einsatzstatistik · {scope}", text, body, reply_to=a.email)
    except (smtplib.SMTPException, OSError) as e:
        log.error("Feedback über %s nicht versendet: %s", mail.SMTP_HOST, e)
        with _lock:
            _last_sent.pop(a.email, None)
        raise HTTPException(502, "Feedback konnte nicht gesendet werden. Bitte später erneut versuchen.")
    return {"sent": True}
