# -*- coding: utf-8 -*-
"""Erinnerung an das Ablaufen der G26.3 per E-Mail (Opt-in je Person: 2 Monate, 1 Monat, 2 Wochen vorher).

Die Mail geht nur an die eigene, im Personenstamm hinterlegte Adresse – und nur, wenn diese Adresse sich schon einmal
angemeldet hat und heute noch das Recht auf die eigene Atemschutz-Ansicht in dieser Wehr hat (Tippfehler in der Adresse
verraten so nichts an Fremde). Inhalt: nur das Ablaufdatum, keine weiteren Angaben. Ein Lauf je Stunde; jede Erinnerung
wird je Person, Ablaufdatum und Stufe höchstens einmal gesendet (agt_reminder_sent).
"""
import asyncio
import datetime as dt
import html
import logging
import os
import smtplib

from app import atemschutz, auth, login_mail, mail, tenancy
from app.rbac import AGT_OWN

log = logging.getLogger("openeinsatzstatistik")
HOUR = int(os.environ.get("AGT_REMINDER_HOUR") or 6)      # frühestens ab dieser Uhrzeit (lokal)
SUBJECT = "Erinnerung: G26.3 läuft bald ab"


def due_offset(valid_until, offsets, today, sent=()):
    """Stufe, die heute zu senden ist (die engste erreichte, noch nicht gesendete), und alle erreichten Stufen.
    Abgelaufene G26.3 erinnert nicht mehr; verpasste frühere Stufen werden nicht nachgeholt."""
    days_left = (valid_until - today).days
    if days_left < 0:
        return None, []
    reached = sorted(o for o in offsets if days_left <= o)
    if not reached or reached[0] in sent:
        return None, reached
    return reached[0], reached


def _text(valid_until, link):
    day = valid_until.strftime("%d.%m.%Y")
    return (f"Deine Untersuchung nach G26.3 läuft am {day} ab. Bitte rechtzeitig einen Termin vereinbaren.\n\n"
            f"Zur Atemschutz-Dokumentation: {link}\n\n"
            "Du erhältst diese Erinnerung, weil du sie in der Atemschutz-Dokumentation eingeschaltet hast; dort kannst du "
            "sie auch wieder abschalten.")


def build(tenant, valid_until, link):
    """-> (Betreff, Text, HTML, Bilder) im Aussehen der Wehr."""
    pal = login_mail._colors(tenant)
    logo = login_mail._logo(tenant)
    images = [(login_mail.LOGO_CID, logo[0], logo[1])] if logo else []
    day = valid_until.strftime("%d.%m.%Y")
    head = (f'<img src="cid:{login_mail.LOGO_CID}" alt="" height="40" style="display:block;border:0;height:40px;width:auto">'
            if logo else "")
    brand, pale = pal["--brand"], pal["--brand-pale"]
    body = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:{pale}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{pale}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:100%;max-width:480px;background:#ffffff;border-radius:8px;overflow:hidden;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#222222">
<tr><td bgcolor="{brand}" style="background:{brand};padding:16px 24px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr><td style="padding-right:12px">{head}</td>
<td style="color:#ffffff;font-size:18px;font-weight:600">{html.escape(tenant.name)}</td></tr></table></td></tr>
<tr><td style="padding:24px;font-size:16px;line-height:1.5">
<p style="margin:0 0 12px">Hallo,</p>
<p style="margin:0 0 16px">deine Untersuchung nach G26.3 läuft am <strong>{day}</strong> ab. Bitte rechtzeitig einen Termin vereinbaren.</p>
<p style="margin:0 0 8px"><a href="{html.escape(link)}" style="display:inline-block;background:{brand};color:#ffffff;text-decoration:none;font-weight:600;padding:12px 24px;border-radius:6px">Zur Atemschutz-Dokumentation</a></p>
</td></tr>
<tr><td bgcolor="{pale}" style="background:{pale};padding:14px 24px;font-size:13px;line-height:1.5;color:#555555">
Du erhältst diese Erinnerung, weil du sie eingeschaltet hast. In der Atemschutz-Dokumentation kannst du sie wieder abschalten.</td></tr>
</table></td></tr></table></body></html>"""
    return SUBJECT, _text(valid_until, link), body, images


def _may_receive(tenant, email):
    """Adresse hat sich schon angemeldet und darf in dieser Wehr die eigene Atemschutz-Ansicht nutzen."""
    with tenancy.central() as con:
        row = con.execute("SELECT last_login FROM account WHERE email = ?", (email,)).fetchone()
    if not row or not row["last_login"]:
        return False
    found = tenancy.access_for(email, f"t:{tenant.slug}").tenants.get(tenant.slug)
    return bool(found and found.can(AGT_OWN))


def run_once(tenants, today=None, send=None):
    """Alle fälligen Erinnerungen senden -> Zahl der gesendeten Mails. Fehler einer Person stoppen die anderen nicht."""
    send = send or mail.send
    today = today or dt.date.today()
    sent_count = 0
    for tenant in tenants:
        with tenant.connection() as con:
            candidates = atemschutz.reminder_candidates(con)
        for member_id, email, valid_until, offsets in candidates:
            try:
                day = dt.date.fromisoformat(valid_until)
                with tenant.connection() as con:
                    done = {r["offset_days"] for r in con.execute(
                        "SELECT offset_days FROM agt_reminder_sent WHERE member_id = ? AND valid_until = ?",
                        (member_id, valid_until))}
                offset, reached = due_offset(day, offsets, today, done)
                if offset is None and not reached:
                    continue
                if offset is not None:
                    if not _may_receive(tenant, email):
                        continue
                    link = auth.BASE_URL or ""
                    subject, text, body, images = build(tenant, day, link)
                    send(email, subject, text, body, images=images)
                    sent_count += 1
                with tenant.connection() as con:       # erst nach erfolgreichem Versand; erreichte Stufen gelten als erledigt
                    con.executemany("INSERT OR IGNORE INTO agt_reminder_sent (member_id, valid_until, offset_days) "
                                    "VALUES (?, ?, ?)", [(member_id, valid_until, o) for o in reached])
            except (smtplib.SMTPException, OSError) as e:
                log.error("Erinnerung an die G26.3 nicht gesendet (Wehr %s): %s", tenant.slug, e)
            except Exception:
                log.exception("Erinnerung an die G26.3 fehlgeschlagen (Wehr %s)", tenant.slug)
    return sent_count


async def run(stop, tenants, interval=3600):
    """Stündlich prüfen (ab HOUR Uhr); nur mit eingerichtetem Mailversand."""
    while not stop.is_set():
        if mail.enabled() and dt.datetime.now().hour >= HOUR:
            try:
                await asyncio.to_thread(lambda: run_once(tenants()))
            except Exception:
                log.exception("Erinnerungen an die G26.3 werden beim nächsten Durchlauf wiederholt")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass
