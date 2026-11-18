# -*- coding: utf-8 -*-
"""
Anmeldemail im Aussehen der zugeordneten Wehr (Farben, Logo, Name) mit Link und Anmeldecode.

Mailprogramme kennen keine CSS-Variablen: Die Farben kommen als feste Werte aus `theme.palette`, das
Layout ist eine Tabelle mit Inline-Styles. Das Logo wird als Bild eingebettet (cid:), weil die Logo-Adresse
der Oberfläche eine Anmeldung verlangt und Gmail keine data:-Adressen anzeigt.

Der Code steht als reine Ziffernfolge mit eindeutigem Satz davor und nur einmal im Text, damit Mailprogramme
ihn als Einmalcode erkennen können. Eine Zusage dafür gibt es für E-Mail nicht (anders als bei SMS).
"""
import html

from app import theme

LOGO_CID = "wehr-logo"
MAX_LOGO_BYTES = 200 * 1024
SUBJECT = "Anmeldung Einsatzstatistik"


def _logo(tenant):
    """(Bytes, MIME-Typ) des hellen Logos der Wehr oder None (fehlt, zu groß, kein Bild)."""
    try:
        with tenant.connection() as con:
            row = con.execute("SELECT data FROM asset WHERE name = 'logo-light'").fetchone()
    except Exception:       # Wehr-DB nicht lesbar: die Mail geht trotzdem neutral hinaus
        return None
    if not row or not row["data"] or len(row["data"]) > MAX_LOGO_BYTES:
        return None
    mime = theme.image_type(bytes(row["data"]))
    return (bytes(row["data"]), mime) if mime else None


DEFAULT_BRAND = {"brand": "#7C2734"}      # Standardfarbe der Oberfläche (app.css, docs/marke.md)


def _colors(tenant):
    """Farben der Wehr; ohne eigene Farbe oder bei Fehlern die Standardfarbe der Oberfläche."""
    try:
        colors = tenant.config.colors if tenant else None
        return theme.palette(colors if theme.normalize(colors) else DEFAULT_BRAND)
    except Exception:
        return theme.palette(DEFAULT_BRAND)


def build(tenant, link, code, ttl_minutes):
    """-> (Betreff, Text, HTML, Bilder) für mail.send. tenant None = neutrales Aussehen."""
    pal = _colors(tenant)
    name = tenant.name if tenant else "Einsatzstatistik"
    subject = f"{SUBJECT} · {tenant.name}" if tenant else SUBJECT
    logo = _logo(tenant) if tenant else None
    images = [(LOGO_CID, logo[0], logo[1])] if logo else []

    text = (f"Dein Anmeldecode: {code}\n\n"
            f"Oder melde dich mit diesem Link bei der Einsatzstatistik ({name}) an:\n{link}\n\n"
            f"Code und Link gelten {ttl_minutes} Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, "
            "kannst du diese Mail ignorieren.")

    brand, dark, pale, light = pal["--brand"], pal["--brand-dark"], pal["--brand-pale"], pal["--brand-light"]
    head = (f'<img src="cid:{LOGO_CID}" alt="" height="40" style="display:block;border:0;height:40px;width:auto">'
            if logo else "")
    body = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:{pale}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{pale}"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="480" cellpadding="0" cellspacing="0" style="width:100%;max-width:480px;background:#ffffff;border-radius:8px;overflow:hidden;font-family:-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#222222">
<tr><td bgcolor="{brand}" style="background:{brand};padding:16px 24px">
<table role="presentation" cellpadding="0" cellspacing="0"><tr>
<td style="padding-right:12px">{head}</td>
<td style="color:#ffffff;font-size:18px;font-weight:600;line-height:1.3">{html.escape(name)}</td></tr></table></td></tr>
<tr><td style="padding:24px 24px 8px;font-size:16px;line-height:1.5">
<p style="margin:0 0 12px">Hallo,</p>
<p style="margin:0 0 12px">dein Anmeldecode für die Einsatzstatistik:</p>
<p style="margin:0 0 20px;padding:14px 12px;background:{light};border-radius:6px;text-align:center;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:30px;letter-spacing:4px;font-weight:700;color:{dark}">{html.escape(code)}</p>
<p style="margin:0 0 12px">Oder melde dich direkt mit diesem Knopf an:</p>
<p style="margin:0 0 20px"><a href="{html.escape(link)}" style="display:inline-block;background:{brand};color:#ffffff;text-decoration:none;font-weight:600;padding:12px 24px;border-radius:6px">Jetzt anmelden</a></p>
</td></tr>
<tr><td bgcolor="{pale}" style="background:{pale};padding:14px 24px;font-size:13px;line-height:1.5;color:#555555">
Code und Link gelten {ttl_minutes} Minuten und nur einmal. Wenn du keine Anmeldung angefordert hast, kannst du diese Mail ignorieren.</td></tr>
</table></td></tr></table></body></html>"""
    return subject, text, body, images
