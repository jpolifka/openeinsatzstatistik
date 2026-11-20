"""Rechtliche Pflichtseiten: Impressum, Datenschutzerklärung, Erklärung zur Barrierefreiheit.

Ohne Anmeldung erreichbar (`/impressum`, `/datenschutz`, `/barrierefreiheit`). Die Angaben zum Betreiber
kommen aus der Umgebung (`LEGAL_*`, siehe .env.example); was fehlt, erscheint als „[bitte ergänzen]“.
Die Texte sind eine Vorlage und gehören vor dem Betrieb rechtlich geprüft.
"""
import html
import logging
import os

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app import theme

log = logging.getLogger("uvicorn.error")
router = APIRouter()

MISSING = "[bitte ergänzen]"
PAGES = {"impressum": "Impressum", "datenschutz": "Datenschutzerklärung", "barrierefreiheit": "Barrierefreiheit"}


def operator():
    """Angaben zum Betreiber; Name und Anschrift sind vorbelegt, E-Mail und Telefon müssen gesetzt werden."""
    def env(key, default=""):
        return os.environ.get(key, "").strip() or default
    return {"name": env("LEGAL_NAME", "Polifka IT-Beratung"),
            "address": env("LEGAL_ADDRESS", "In der Maar 31, 56598 Rheinbrohl"),
            "representative": env("LEGAL_REPRESENTATIVE"), "email": env("LEGAL_EMAIL", MISSING),
            "phone": env("LEGAL_PHONE"), "vat_id": env("LEGAL_VAT_ID"),
            "hosting": env("DPA_HOSTING"), "mail_provider": env("DPA_MAIL_PROVIDER")}


def check_config():
    if operator()["email"] == MISSING:
        log.warning("LEGAL_EMAIL fehlt – das Impressum ist unvollständig (siehe .env.example)")


def _e(value):
    return html.escape(value)


def _address_lines(address):
    return "<br>".join(_e(part.strip()) for part in address.replace(";", ",").split(",", 1))


def _impressum(o):
    rows = [f"<p><b>{_e(o['name'])}</b><br>{_address_lines(o['address'])}</p>"]
    if o["representative"]:
        rows.append(f"<p>Vertreten durch: {_e(o['representative'])}</p>")
    contact = [f"E-Mail: <a href=\"mailto:{_e(o['email'])}\">{_e(o['email'])}</a>"]
    if o["phone"]:
        contact.append(f"Telefon: {_e(o['phone'])}")
    rows.append("<h2>Kontakt</h2><p>" + "<br>".join(contact) + "</p>")
    if o["vat_id"]:
        rows.append(f"<h2>Umsatzsteuer-ID</h2><p>{_e(o['vat_id'])}</p>")
    rows.append("<h2>Verantwortlich für den Inhalt</h2>"
                f"<p>{_e(o['name'])}, Anschrift wie oben.</p>")
    rows.append("<h2>Hinweis zur Software</h2><p>Die Einsatzstatistik beruht auf der freien Software "
                "<a href=\"https://github.com/jpolifka/openeinsatzstatistik\" rel=\"noopener noreferrer\">"
                "openEinsatzstatistik</a> (AGPL). Die Einsatzdaten gehören den jeweiligen Verbandsgemeinden "
                "bzw. Wehren, die sie erfassen.</p>")
    return "".join(rows)


def _privacy(o):
    hosting = f" Das Hosting erfolgt bei {_e(o['hosting'])}." if o["hosting"] else ""
    mail = f" Die Mails werden über {_e(o['mail_provider'])} versendet." if o["mail_provider"] else ""
    return f"""
<h2>1. Verantwortlicher und Auftragsverarbeitung</h2>
<p>Für Anmeldung, Sitzungen und den technischen Betrieb ist verantwortlich: {_e(o['name'])},
{_e(o['address'])}, E-Mail: {_e(o['email'])}.</p>
<p>Die <b>Einsatzdaten</b> (Berichte, Einsätze, Anwesenheiten, Personal) verarbeitet {_e(o['name'])} im Auftrag der
jeweiligen Verbandsgemeinde bzw. Stadt auf Grundlage eines Vertrags zur Auftragsverarbeitung (Art. 28 DSGVO).
Verantwortlich im Sinne der DSGVO ist dort die Verbandsgemeinde bzw. Stadt. Für Auskunft, Berichtigung und
Löschung wenden Sie sich bitte an die Wehrleitung bzw. die Verwaltung Ihrer Verbandsgemeinde.</p>

<h2>2. Welche Daten wir verarbeiten</h2>
<ul>
<li><b>Anmeldung:</b> Ihre E-Mail-Adresse. Wir senden Ihnen einen Anmeldelink und einen Code. Beides gilt
15 Minuten und einmal; gespeichert wird nur eine Prüfsumme davon. Fehlversuche werden kurz gezählt, um Missbrauch zu begrenzen.</li>
<li><b>Sitzung:</b> E-Mail-Adresse, Zeitpunkt von Anmeldung und letzter Nutzung sowie die Browser-Kennung
(User-Agent), damit Sie Ihre Sitzungen erkennen und beenden können. Gültig 30 Tage oder bis zur Abmeldung.</li>
<li><b>Einsatzdaten</b> der Wehr: Berichte aus dem BKS-Portal mit Einsatzdaten, Namen und Anwesenheiten,
Benutzer und Rollen sowie Protokolle der Verwaltung.</li>
<li><b>Rückmeldungen:</b> Nachrichten über das Feedback-Formular werden per E-Mail an die Administratoren
gesendet und nicht in der Anwendung gespeichert.</li>
</ul>
<p>Die Anwendung bindet keine Analyse-, Werbe- oder Tracking-Dienste ein und lädt keine Schriften oder Skripte von
fremden Servern nach.</p>

<h2>3. Rechtsgrundlagen</h2>
<p>Anmeldung und Betrieb: Art. 6 Abs. 1 lit. b bzw. f DSGVO (Bereitstellung der Anwendung, Sicherheit).
Einsatzdaten: Aufgaben der Gefahrenabwehr der Verbandsgemeinde bzw. Stadt (Art. 6 Abs. 1 lit. e DSGVO i. V. m. dem
Brand- und Katastrophenschutzgesetz Rheinland-Pfalz) nach Weisung des Verantwortlichen.</p>

<h2>4. Cookies</h2>
<p>Es werden nur technisch notwendige Cookies gesetzt, die für den Betrieb erforderlich sind und keine
Einwilligung benötigen: <code>session</code> (angemeldete Sitzung) und <code>scope</code> (ausgewählte Wehr).</p>

<h2>5. Empfänger und Hosting</h2>
<p>Die Daten werden in Deutschland bzw. der EU verarbeitet.{hosting}{mail}
Eine Weitergabe an Dritte zu eigenen Zwecken findet nicht statt.</p>

<h2>6. Speicherdauer</h2>
<p>Anmeldecodes und -fehlversuche werden nach kurzer Zeit gelöscht, Sitzungen laufen nach 30 Tagen ab. Einsatzdaten
werden so lange gespeichert, wie die Verbandsgemeinde bzw. Stadt es festlegt.</p>

<h2>7. Ihre Rechte</h2>
<p>Sie haben das Recht auf Auskunft, Berichtigung, Löschung, Einschränkung der Verarbeitung, Datenübertragbarkeit und
Widerspruch (Art. 15–21 DSGVO) sowie das Recht auf Beschwerde bei einer Aufsichtsbehörde, in Rheinland-Pfalz beim
Landesbeauftragten für den Datenschutz und die Informationsfreiheit Rheinland-Pfalz, Hintere Bleiche 34, 55116 Mainz.</p>
"""


def _accessibility(o):
    return f"""
<p>{_e(o['name'])} ist bemüht, die Einsatzstatistik für alle Menschen nutzbar zu machen.</p>

<h2>Stand</h2>
<p>Die Anwendung ist <b>teilweise barrierefrei</b> (Orientierung: WCAG 2.1, Stufe AA). Sie ist ein internes Werkzeug
für Feuerwehren und wird derzeit nicht vollständig gegen diese Anforderungen geprüft.</p>

<h2>Was bereits berücksichtigt ist</h2>
<ul>
<li>Bedienung per Tastatur, Tastenkürzel (Hilfe unter „?“)</li>
<li>Diagramme lassen sich als Tabelle anzeigen</li>
<li>Beschriftete Eingabefelder und Schaltflächen, deutsche Sprachauszeichnung</li>
<li>Farbkontraste werden bei Wehr-Farben automatisch geprüft und angepasst</li>
</ul>

<h2>Bekannte Einschränkungen</h2>
<ul>
<li>Einzelne Diagramme und Kartendarstellungen sind für Screenreader nur über die Tabellenansicht vollständig nutzbar.</li>
<li>Hochgeladene PDF-Dokumente (z. B. Verträge) sind nicht in jedem Fall barrierefrei.</li>
</ul>

<h2>Barriere melden</h2>
<p>Stoßen Sie auf eine Barriere oder brauchen Sie Inhalte in einer anderen Form? Schreiben Sie an
<a href="mailto:{_e(o['email'])}">{_e(o['email'])}</a>. Wir antworten in der Regel innerhalb von zwei Wochen.</p>

<h2>Schlichtung</h2>
<p>Bleibt die Rückmeldung unbefriedigend, können Sie sich an die zuständige Marktüberwachungs- bzw. Schlichtungsstelle
wenden (z. B. die Schlichtungsstelle nach § 16 BGG).</p>
"""


BODIES = {"impressum": _impressum, "datenschutz": _privacy, "barrierefreiheit": _accessibility}


def page(key):
    body = BODIES[key](operator())
    title = PAGES[key]
    links = " · ".join(f'<a class="footer-link" href="/{k}">{_e(v)}</a>' for k, v in PAGES.items() if k != key)
    return f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_e(title)} · Einsatzstatistik</title><link rel="icon" href="/static/favicon.svg">
<link rel="stylesheet" href="/static/app.css">
<style>{theme.css(theme.NEUTRAL)}.legal h2{{margin-top:1.4em;font-size:1.1rem}}.legal ul{{padding-left:1.2em}}</style></head>
<body><header class="topbar"><div class="topbar-inner">
<img class="topbar-logo" src="/static/img/app-icon-light.svg" alt="">
<div class="topbar-title"><span class="topbar-kicker">Einsatzstatistik</span><h1>{_e(title)}</h1></div>
</div></header>
<main class="page"><div class="card legal">{body}</div></main>
<footer class="footer"><a class="footer-link" href="/">Zur Anwendung</a><span aria-hidden="true">·</span>{links}</footer>
</body></html>"""


def _route(key):
    def view():
        return HTMLResponse(page(key))
    view.__name__ = f"legal_{key}"
    return view


for _key in PAGES:
    router.add_api_route(f"/{_key}", _route(_key), methods=["GET"], include_in_schema=False)
