# -*- coding: utf-8 -*-
"""
Willkommensmail für Führungspersonen: Wer eine Führungsrolle (Wehrführung, Wehrleitung, Stellvertretung,
Inspekteur, Leitstellenleitung) zugeordnet bekommt, erhält einmal eine Mail mit Anmeldung und ersten Schritten.

- Im Design der Wehr wie die Anmeldemail (`login_mail`), ohne Anmeldelink (der gilt nur 15 Minuten und einmal):
  Die Person fordert Code oder Link selbst auf der Anmeldeseite an.
- Je Person genau einmal (`welcome_sent` der Zentral-DB, Schlüssel = E-Mail), auch bei weiteren Rollen.
  Die Zeile wird vor dem Versand angelegt und bei einem Fehler wieder entfernt: nie doppelt, ein Fehler lässt
  sich wiederholen.
- Nachversand für bereits angelegte Personen: `python -m app.welcome catch-up` zeigt, wer sie bekäme
  (Probelauf), `--send` verschickt sie. Wer sich schon angemeldet hat, wird übergangen (`--include-active` nimmt
  auch sie mit). Im Container als Besitzer von ./daten ausführen (root darf die Datenbank wegen cap_drop nicht öffnen):
  docker compose exec --user "$(stat -c %u:%g daten)" einsatzberichte python -m app.welcome catch-up
- Ein Fehler beim Versand lässt das Zuordnen nie scheitern.
"""
import html
import logging
import smtplib
import sqlite3
import sys

from app import auth, login_mail, mail, tenancy

log = logging.getLogger("openeinsatzstatistik")

# Rollen, die als Führung gelten (Schlüssel der Systemrollen, siehe rbac.SYSTEM_ROLES/BKS_ROLES)
LEADERSHIP = ("lead", "deputy_lead", "vg_lead", "vg_deputy", "bki", "bki_deputy", "dispatch_lead")
SUBJECT = "Willkommen in der Einsatzstatistik"


def leadership_roles(con, email):
    """[(Rollenbezeichnung, Bereich)] der Führungsrollen dieser Person in aktiven Bereichen."""
    marks = ",".join("?" * len(LEADERSHIP))
    rows = con.execute(
        "SELECT r.label AS role, COALESCE(t.name, v.name) AS area FROM membership m JOIN role r ON r.id = m.role_id "
        "LEFT JOIN tenant t ON m.scope = 'tenant' AND t.id = m.scope_id AND t.active "
        "LEFT JOIN vg v ON m.scope = 'vg' AND v.id = m.scope_id "
        f"WHERE m.email = ? AND r.key IN ({marks}) AND COALESCE(t.name, v.name) IS NOT NULL "
        "ORDER BY m.created, m.scope_id", (email, *LEADERSHIP)).fetchall()
    return [(r["role"], r["area"]) for r in rows]


def build(tenant, roles, link):
    """-> (Betreff, Text, HTML, Bilder) für mail.send. tenant None = neutrales Aussehen; roles = [(Rolle, Bereich)]."""
    pal = login_mail._colors(tenant)
    name = tenant.name if tenant else "Einsatzstatistik"
    logo = login_mail._logo(tenant) if tenant else None
    images = [(login_mail.LOGO_CID, logo[0], logo[1])] if logo else []
    subject = f"{SUBJECT} · {tenant.name}" if tenant else SUBJECT

    given = [f"{role} ({area})" for role, area in roles]
    steps = [
        ("Einstellungen prüfen", "Unter Einstellungen stehen Fahrzeuge, Orte, Zeitgrenzen und Stichwortkatalog. "
                                 "Stimmt das mit eurer Wehr überein?"),
        ("Personal pflegen", "Unter Einstellungen → Personen steht, wer zur Wehr gehört. Wer ausscheidet, wird dort "
                             "als ausgeschieden markiert."),
        ("Einsatzberichte einlesen", "Über „Bericht einlesen“ lädst du Berichte aus dem BKS-Portal hoch (PDF oder "
                                     "Excel-Export, einzeln oder als ZIP). Du prüfst die Vorschau und übernimmst sie."),
        ("Auswertungen ansehen", "Unter Auswertungen siehst du Einsatzgeschehen, Zeiten und Kräfte, Belastung und "
                                 "mehr – jeweils mit Angabe, wie viele Einsätze die Zahl trägt."),
        ("Zugänge vergeben", "Weitere Personen (Stellvertretung, Ausbilder, Erfasser) legst du unter Einstellungen → "
                             "Benutzer an. Jede Person meldet sich mit der eigenen E-Mail-Adresse an."),
    ]
    login = ("Es gibt kein Passwort: Öffne die Adresse unten, trage diese E-Mail-Adresse ein und gib den Code ein, "
             "der dir per Mail kommt (oder klicke auf den Link darin).")
    care = ("Die Einsatzdaten enthalten Namen von Kameradinnen und Kameraden. Bitte gib deinen Zugang nicht weiter – "
            "für weitere Personen gibt es eigene Zugänge.")
    help_ = ("Hilfe findest du jederzeit über das „?“ oben rechts; dort gibt es auch einen Reiter, "
             "um uns Fragen und Rückmeldungen zu schicken.")

    text = (f"Hallo,\n\nfür dich wurde in der Einsatzstatistik ({name}) ein Zugang eingerichtet:\n"
            + "".join(f"  • {g}\n" for g in given)
            + f"\nAnmelden: {login}\n{link}\n\nDie ersten Schritte:\n"
            + "".join(f"  {i}. {t}: {d}\n" for i, (t, d) in enumerate(steps, 1))
            + f"\n{care}\n{help_}\n")

    brand, dark, pale, light = pal["--brand"], pal["--brand-dark"], pal["--brand-pale"], pal["--brand-light"]
    head = (f'<img src="cid:{login_mail.LOGO_CID}" alt="" height="40" style="display:block;border:0;height:40px;width:auto">'
            if logo else "")
    roles_html = "".join(f'<li style="margin:0 0 4px">{html.escape(g)}</li>' for g in given)
    steps_html = "".join(
        f'<li style="margin:0 0 8px"><b>{html.escape(t)}.</b> {html.escape(d)}</li>' for t, d in steps)
    body = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:{pale}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{pale}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="520" cellpadding="0" cellspacing="0" style="width:100%;max-width:520px;background:#ffffff;border-radius:8px;overflow:hidden;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#222222">
<tr><td bgcolor="{brand}" style="background:{brand};padding:16px 24px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding-right:12px">{head}</td>
<td style="color:#ffffff;font-size:18px;font-weight:600;line-height:1.3">{html.escape(name)}</td></tr></table></td></tr>
<tr><td style="padding:24px 24px 8px;font-size:16px;line-height:1.5">
<p style="margin:0 0 12px;font-size:20px;font-weight:600;color:{dark}">Willkommen in der Einsatzstatistik</p>
<p style="margin:0 0 8px">für dich wurde ein Zugang eingerichtet:</p>
<ul style="margin:0 0 16px;padding:12px 12px 12px 32px;background:{light};border-radius:6px">{roles_html}</ul>
<p style="margin:0 0 12px">{html.escape(login)}</p>
<p style="margin:0 0 20px"><a href="{html.escape(link)}" style="display:inline-block;background:{brand};color:#ffffff;text-decoration:none;font-weight:600;padding:12px 24px;border-radius:6px">Zur Anmeldung</a></p>
<p style="margin:0 0 8px;font-weight:600;color:{dark}">Die ersten Schritte</p>
<ol style="margin:0 0 16px;padding-left:22px">{steps_html}</ol>
</td></tr>
<tr><td bgcolor="{pale}" style="background:{pale};padding:14px 24px;font-size:13px;line-height:1.5;color:#555555">
{html.escape(care)}<br>{html.escape(help_)}</td></tr>
</table></td></tr></table></body></html>"""
    return subject, text, body, images


def send_welcome(email):
    """Schickt die Willkommensmail, wenn die Person Führungsrollen hat und noch keine bekam.
    -> "sent", "failed", "unavailable" (kein Mailversand), "skipped" (keine Führungsrolle oder schon erhalten)."""
    email = tenancy.normalize_email(email)
    if not mail.enabled():
        return "unavailable"
    with tenancy.central() as con:
        roles = leadership_roles(con, email)
        if not roles or con.execute("INSERT OR IGNORE INTO welcome_sent (email) VALUES (?)", (email,)).rowcount == 0:
            return "skipped"
    try:
        try:
            subject, text, body, images = build(tenancy.mail_tenant(email), roles, auth.link_base(email) or "")
        except Exception:        # Gestaltung der Wehr darf den Versand nie verhindern
            log.exception("Gestaltung der Willkommensmail fehlgeschlagen, neutrale Mail")
            subject, text, body, images = build(None, roles, auth.link_base(email) or "")
        mail.send(email, subject, text, body, images=images)
    except (smtplib.SMTPException, OSError) as e:
        safe = email.replace("\r", "").replace("\n", "")      # kein Zeilenumbruch aus Eingaben ins Log
        log.error("Willkommensmail an %s nicht versendet: %s", safe, e)
        _forget(email)
        return "failed"
    except Exception:
        _forget(email)
        raise
    return "sent"


def _forget(email):
    with tenancy.central() as con:
        con.execute("DELETE FROM welcome_sent WHERE email = ?", (email,))


def pending(include_active=False):
    """Personen mit Führungsrolle ohne Willkommensmail (sortiert); Angemeldete nur mit include_active."""
    with tenancy.central() as con:
        marks = ",".join("?" * len(LEADERSHIP))
        rows = con.execute(
            "SELECT DISTINCT m.email FROM membership m JOIN role r ON r.id = m.role_id "
            "JOIN account a ON a.email = m.email "
            f"WHERE r.key IN ({marks}) AND NOT EXISTS (SELECT 1 FROM welcome_sent w WHERE w.email = m.email) "
            + ("" if include_active else "AND a.last_login IS NULL ") + "ORDER BY m.email", LEADERSHIP).fetchall()
        return [r["email"] for r in rows if leadership_roles(con, r["email"])]


def catch_up(send=False, include_active=False):
    """Nachversand für bereits angelegte Personen. Ohne send nur der Probelauf. -> {E-Mail: Ergebnis}."""
    result = {}
    for email in pending(include_active):
        result[email] = send_welcome(email) if send else "would_send"
    return result


def main(argv):
    if argv[:1] != ["catch-up"]:
        print("Aufruf: python -m app.welcome catch-up [--send] [--include-active]")
        return 2
    flags = set(argv[1:])
    send = "--send" in flags
    if send and not mail.enabled():
        print("SMTP_HOST ist nicht gesetzt – kein Versand möglich.")
        return 1
    try:
        result = catch_up(send, "--include-active" in flags)
    except sqlite3.OperationalError as e:
        print(f"Die Datenbank lässt sich nicht öffnen ({e}). Im Container als Besitzer des Datenordners aufrufen:\n"
              '  docker compose exec --user "$(stat -c %u:%g daten)" einsatzberichte python -m app.welcome catch-up')
        return 1
    for email, state in result.items():
        print(f"{email}\t{state}")
    if not send:
        print(f"\nProbelauf: {len(result)} Person(en) würden die Mail bekommen. Versand mit --send.")
    return 1 if "failed" in result.values() else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
