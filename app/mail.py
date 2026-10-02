# -*- coding: utf-8 -*-
"""
E-Mail-Versand per SMTP über das Postfach der eigenen Domain (z. B. Strato) – ohne Dritt-Dienst.

DMARC (p=reject) lässt eine Mail nur durch, wenn SPF oder DKIM zur Domain im From passt:
- SPF: Envelope-From ist die Adresse aus MAIL_FROM; eingeliefert wird über den SMTP-Server des
  Domain-Anbieters, dessen Ausgangsserver im SPF-Eintrag der Domain stehen.
- DKIM: die App signiert jede Mail selbst (d=<Domain aus MAIL_FROM>, Selektor DKIM_SELECTOR). Der
  öffentliche Schlüssel steht als TXT unter <selektor>._domainkey.<domain>. Damit besteht DMARC auch
  dann, wenn eine Mail weitergeleitet wird und SPF dabei bricht.

Befehle (im Container: docker compose exec einsatzberichte python -m app.mail …):
  dkim-key   Schlüssel erzeugen (DKIM_KEY_FILE) und den DNS-Eintrag ausgeben
  check      SPF, DKIM und DMARC der Absenderdomain im DNS prüfen
  test ADR   Test-Mail an ADR senden
"""
import base64
import email.policy
import email.utils
import logging
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage

import dkim
import dns.exception
import dns.resolver
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

log = logging.getLogger("pdf2einsatz")

SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT") or 0)
SMTP_SECURITY = os.environ.get("SMTP_SECURITY", "").lower()     # ssl (Port 465) oder starttls (Port 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "")
DKIM_SELECTOR = os.environ.get("DKIM_SELECTOR", "")
DKIM_KEY_FILE = os.environ.get("DKIM_KEY_FILE", "")
TIMEOUT = 15
# Signierte Kopfzeilen; Date und Message-ID schützen gegen Wiederverwendung der Signatur
SIGNED_HEADERS = [b"from", b"to", b"subject", b"date", b"message-id", b"reply-to", b"mime-version",
                  b"content-type"]


def enabled():
    return bool(SMTP_HOST)


def sender():
    """(Anzeigename, Adresse, Domain) aus MAIL_FROM."""
    name, address = email.utils.parseaddr(MAIL_FROM)
    return name, address, address.rpartition("@")[2].lower()


def check_config():
    """Bricht den Start ab, wenn der Versand so nicht funktionieren kann."""
    if not SMTP_HOST:
        return
    _, address, domain = sender()
    if "@" not in address or not domain:
        raise RuntimeError("SMTP_HOST ist gesetzt, MAIL_FROM fehlt oder ist keine Adresse (siehe README)")
    if SMTP_SECURITY not in ("ssl", "starttls"):
        raise RuntimeError("SMTP_SECURITY muss ssl (Port 465) oder starttls (Port 587) sein")
    if not SMTP_PORT or not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP_PORT, SMTP_USER und SMTP_PASSWORD fehlen (siehe README)")
    if bool(DKIM_SELECTOR) != bool(DKIM_KEY_FILE):
        raise RuntimeError("DKIM_SELECTOR und DKIM_KEY_FILE nur zusammen setzen")
    if DKIM_KEY_FILE and not os.path.exists(DKIM_KEY_FILE):
        raise RuntimeError(f"DKIM-Schlüssel {DKIM_KEY_FILE} fehlt – erzeugen mit: python -m app.mail dkim-key")


# ---------------------------------------------------------------- Mail bauen und senden
def build(to, subject, text, html, reply_to=None):
    name, address, domain = sender()
    msg = EmailMessage()
    msg["From"] = email.utils.formataddr((name, address))
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid(domain=domain)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    return msg


def _private_key():
    with open(DKIM_KEY_FILE, "rb") as f:
        return f.read()


def sign(data):
    """DKIM-Signatur (rsa-sha256, relaxed/relaxed) vor die Mail setzen."""
    _, _, domain = sender()
    signature = dkim.sign(data, DKIM_SELECTOR.encode(), domain.encode(), _private_key(),
                          canonicalize=(b"relaxed", b"relaxed"), include_headers=SIGNED_HEADERS)
    return signature + data


def send(to, subject, text, html, reply_to=None):
    """Mail über den SMTP-Server des Domain-Anbieters einliefern; Fehler als smtplib.SMTPException/OSError."""
    _, address, _ = sender()
    # SMTP verlangt CRLF als Zeilenende; smtplib wandelt Bytes nicht um (sonst 554 bei Strato).
    # Signiert wird danach genau das, was eingeliefert wird.
    data = build(to, subject, text, html, reply_to).as_bytes(policy=email.policy.SMTP)
    if DKIM_SELECTOR:
        data = sign(data)
    context = ssl.create_default_context()
    if SMTP_SECURITY == "ssl":
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT, context=context)
    else:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT)
    with server:
        if SMTP_SECURITY == "starttls":
            server.starttls(context=context)
        server.login(SMTP_USER, SMTP_PASSWORD)
        # Envelope-From = Absenderadresse: SPF wird für die eigene Domain geprüft (DMARC-Ausrichtung)
        server.sendmail(address, [to], data)


# ---------------------------------------------------------------- DKIM-Schlüssel und DNS-Prüfung
def public_key_record(private_pem):
    """TXT-Wert für <selektor>._domainkey.<domain> zum privaten Schlüssel."""
    key = serialization.load_pem_private_key(private_pem, password=None)
    der = key.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    return "v=DKIM1; k=rsa; p=" + base64.b64encode(der).decode()


def generate_key(path):
    """Neuen 2048-Bit-Schlüssel anlegen (nie überschreiben) und den DNS-Eintrag zurückgeben."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption())
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as f:
        f.write(pem)
    return public_key_record(pem)


def txt(name):
    """TXT-Einträge eines Namens als Texte (leer, wenn es keine gibt)."""
    try:
        answers = dns.resolver.resolve(name, "TXT", lifetime=5)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        return []
    return [b"".join(r.strings).decode(errors="replace") for r in answers]


def _tags(record):
    return {k.strip().lower(): v.strip() for k, _, v in (part.partition("=") for part in record.split(";")) if k.strip()}


def check():
    """[(ok, Meldung)] zu SPF, DKIM und DMARC der Absenderdomain. ok=None heißt: nur Hinweis."""
    _, _, domain = sender()
    if not domain:
        return [(False, "MAIL_FROM fehlt")]
    results = []
    try:
        spf = [r for r in txt(domain) if r.lower().startswith("v=spf1")]
        if len(spf) != 1:
            results.append((False, f"SPF: {len(spf)} Einträge für {domain} (genau einer nötig)"))
        elif {"all", "+all", "?all"} & set(spf[0].lower().split()):
            results.append((False, f"SPF von {domain} erlaubt jedem Server zu senden: {spf[0]}"))
        else:
            results.append((True, f"SPF: {spf[0]} – der SMTP-Server {SMTP_HOST or '?'} muss dazu gehören"))

        dkim_ok = False
        if DKIM_SELECTOR:
            name = f"{DKIM_SELECTOR}._domainkey.{domain}"
            published = [_tags(r).get("p", "").replace(" ", "") for r in txt(name)]
            expected = _tags(public_key_record(_private_key()))["p"]
            dkim_ok = expected in published
            results.append((dkim_ok, f"DKIM: {name} " + ("passt zum Schlüssel" if dkim_ok else
                            "fehlt oder passt nicht zum Schlüssel – Eintrag aus „python -m app.mail dkim-key“ setzen")))
        else:
            results.append((None, "DKIM: die App signiert nicht (DKIM_SELECTOR leer) – DMARC hängt dann allein an SPF"))

        dmarc = [r for r in txt(f"_dmarc.{domain}") if r.lower().startswith("v=dmarc1")]
        if not dmarc:
            results.append((False, f"DMARC: kein Eintrag unter _dmarc.{domain}"))
        else:
            tags = _tags(dmarc[0])
            strict = [name for key, name in (("adkim", "DKIM"), ("aspf", "SPF")) if tags.get(key) == "s"]
            results.append((True, f"DMARC: p={tags.get('p', '?')}"
                            + (f", strenge Ausrichtung für {' und '.join(strict)} – passt, da From = Domain" if strict else "")))
    except dns.exception.DNSException as e:
        results.append((None, f"DNS nicht erreichbar ({type(e).__name__}) – Prüfung übersprungen"))
    return results


def log_check():
    """Beim Start: Ergebnis der DNS-Prüfung ins Log (blockiert nicht – das DNS kann gerade fehlen)."""
    if not enabled():
        return
    for ok, message in check():
        (log.info if ok else log.warning)("Mailversand: %s", message)


def main(argv):
    if argv[:1] == ["dkim-key"]:
        path = argv[1] if len(argv) > 1 else DKIM_KEY_FILE
        if not path:
            sys.exit("Pfad fehlt: python -m app.mail dkim-key <datei> oder DKIM_KEY_FILE setzen")
        record = generate_key(path)
        _, _, domain = sender()
        print(f"Schlüssel: {path}\nDNS-Eintrag (TXT) unter {DKIM_SELECTOR or '<selektor>'}._domainkey.{domain or '<domain>'}:\n{record}")
    elif argv[:1] == ["check"]:
        results = check()
        for ok, message in results:
            print({True: "OK  ", False: "FEHL", None: "INFO"}[ok], message)
        sys.exit(0 if all(ok is not False for ok, _ in results) else 1)
    elif argv[:1] == ["test"] and len(argv) == 2:
        check_config()
        send(argv[1], "Test Einsatzstatistik", "Test-Mail der Einsatzstatistik.", "<p>Test-Mail der Einsatzstatistik.</p>")
        print(f"gesendet an {argv[1]} über {SMTP_HOST}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
