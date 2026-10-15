# -*- coding: utf-8 -*-
"""
Auftragsverarbeitungsvertrag (AVV) je Verbandsgemeinde.

Die VG ist als Träger der Feuerwehr Verantwortliche, der Betreiber Auftragsverarbeiter. Solange
für eine VG kein AVV vorliegt (Status pending, draft, revoked), sind ihre Wehren für alle außer
Superadmins gesperrt (tenancy.access_for): Zugeordnete sehen nur diese Seite.

Ablauf: Formular ausfüllen -> Vertrag aus der Vorlage erzeugen (Prüfsumme des Textes wird
gespeichert) -> außerhalb der App unterschreiben -> unterschriebenes PDF hochladen und/oder Link
auf die Ablage der VG hinterlegen -> der Superadmin bestätigt (signed). Alle Schritte stehen in
dpa_event (nur anhängen). Hochgeladene Dateien werden nie überschrieben.
"""
import datetime as dt
import hashlib
import html
import json
import logging
import os
import re
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app import auth, db, rbac, tenancy

log = logging.getLogger("pdf2einsatz")
router = APIRouter()
access = auth.access

TEMPLATE_VERSION = 2          # 2: Mailversand über das eigene Postfach statt Resend
TEMPLATES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
STATUSES = {
    "pending": "AVV ausstehend",
    "draft": "ausgefüllt – Unterschrift ausstehend",
    "signed": "AVV liegt vor",
    "revoked": "zurückgenommen",
    "not_required": "nicht erforderlich (Eigenbetrieb)",
}
OPEN = {"pending", "draft", "revoked"}            # Wehren der VG gesperrt
CLIENT_FIELDS = (("client_name", "Auftraggeber (Verbandsgemeinde bzw. Gemeinde)"), ("client_address", "Anschrift"),
                 ("client_representative", "vertreten durch (z. B. Bürgermeister/in)"),
                 ("client_dpo", "Datenschutzbeauftragte/r (Name, Kontakt)"),
                 ("client_contact", "Ansprechpartner Feuerwehr (Name, E-Mail)"))
MISSING = "[bitte ergänzen]"
MAX_PDF_BYTES = 10 * 1024 * 1024


def processor():
    """Angaben zum Auftragnehmer aus der Umgebung (siehe .env.example)."""
    env = lambda key: os.environ.get(key, "").strip() or MISSING  # noqa: E731
    return {"processor_name": "Polifka IT Beratung", "processor_address": env("DPA_PROCESSOR_ADDRESS"),
            "processor_representative": env("DPA_PROCESSOR_REPRESENTATIVE"),
            "processor_contact": env("DPA_PROCESSOR_CONTACT"), "hosting": env("DPA_HOSTING"),
            "hosting_location": env("DPA_HOSTING_LOCATION"), "backup": env("DPA_BACKUP"),
            "mail_provider": env("DPA_MAIL_PROVIDER"), "mail_location": env("DPA_MAIL_LOCATION")}


# ---------------------------------------------------------------- Datenbank
def status(con, vg_id):
    row = con.execute("SELECT * FROM dpa WHERE vg_id = ?", (vg_id,)).fetchone()
    return dict(row) if row else {"vg_id": vg_id, "status": "pending", "client_data": "{}"}


def open_vgs(con):
    """IDs der VGs ohne gültigen AVV (fehlende Zeile = ausstehend)."""
    done = {r[0] for r in con.execute("SELECT vg_id FROM dpa WHERE status NOT IN ('pending', 'draft', 'revoked')")}
    return {r[0] for r in con.execute("SELECT id FROM vg")} - done


def _save(con, vg_id, **values):
    con.execute("INSERT INTO dpa (vg_id) VALUES (?) ON CONFLICT(vg_id) DO NOTHING", (vg_id,))
    assignments = ", ".join(f"{k} = ?" for k in values)
    con.execute(f"UPDATE dpa SET {assignments}, updated = datetime('now', 'localtime') WHERE vg_id = ?",
                [*values.values(), vg_id])


def event(con, vg_id, email, action, detail=""):
    con.execute("INSERT INTO dpa_event (vg_id, email, action, detail) VALUES (?, ?, ?, ?)",
                (vg_id, email or "lokal", action, detail))


def set_status(con, vg_id, new_status, email, detail=""):
    _save(con, vg_id, status=new_status)
    event(con, vg_id, email, f"Status: {STATUSES[new_status]}", detail)


# ---------------------------------------------------------------- Dokument
def render(client_data, tenant_names, version=TEMPLATE_VERSION):
    """Vertragstext (HTML-Ausschnitt) aus der Vorlage und seine Prüfsumme (SHA-256). Ein erzeugter Vertrag
    wird immer mit der Vorlage gezeigt, aus der er entstand."""
    with open(os.path.join(TEMPLATES, f"avv_v{version}.html"), encoding="utf-8") as f:
        text = f.read()
    values = {**processor(), **{key: (client_data.get(key) or "").strip() or MISSING for key, _ in CLIENT_FIELDS},
              "tenants": ", ".join(tenant_names) or MISSING, "template_version": str(version)}
    body = re.sub(r"\{\{(\w+)\}\}", lambda m: html.escape(values.get(m.group(1), MISSING)).replace("\n", "<br>"), text)
    return body, hashlib.sha256(body.encode("utf-8")).hexdigest()


def page(body, checksum, title, generated=None, nonce=""):
    changed = ('<p class="warning noprint">Der Text weicht vom erzeugten Vertrag ab (Prüfsumme damals: '
               f'{generated}). Bitte den Vertrag neu erzeugen.</p>') if generated and generated != checksum else ""
    return f"""<!doctype html><html lang="de"><head><meta charset="utf-8"><title>{html.escape(title)}</title>
<style>
body {{ font: 11pt/1.45 Georgia, "Times New Roman", serif; color: #222; max-width: 820px; margin: 30px auto; padding: 0 24px; }}
h1 {{ font-size: 20pt; margin: 0; }} h2 {{ font-size: 12.5pt; margin: 22px 0 6px; }} h3 {{ font-size: 11pt; margin: 14px 0 4px; }}
.subtitle {{ margin: 4px 0 18px; color: #555; }} p {{ margin: 6px 0; text-align: justify; }}
table {{ width: 100%; border-collapse: collapse; margin: 10px 0; }} th, td {{ border: 1px solid #bbb; padding: 6px 8px; vertical-align: top; text-align: left; }}
.signatures td {{ border: 0; width: 50%; padding: 4px 12px 4px 0; }} .signatures td.line {{ border-bottom: 1px solid #222; height: 48px; }}
.annex {{ page-break-before: always; }} .note, .checksum {{ color: #666; font-size: 9pt; margin-top: 24px; }}
.warning {{ background: #FFF2CC; padding: 8px 12px; border-radius: 6px; }}
@media print {{ body {{ margin: 0 auto; }} .noprint {{ display: none; }} }}
</style></head><body>
<p class="noprint"><button id="print-button">Drucken / als PDF sichern</button></p>
{changed}{body}
<p class="checksum">Prüfsumme des Vertragstextes (SHA-256): {checksum}</p>
<script nonce="{nonce}">document.getElementById("print-button").addEventListener("click", () => print());</script>
</body></html>"""


# ---------------------------------------------------------------- Rechte
def _vg(con, slug):
    row = con.execute("SELECT id, slug, name FROM vg WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise HTTPException(404, "Verbandsgemeinde nicht gefunden.")
    return row


def rights(con, a, vg_id):
    """'edit' (Recht DPA_EDIT aus einer Rolle der VG oder einer ihrer Wehren, Superadmin), 'view' (DPA_VIEW)
    oder None – unabhängig von der Sperre, die der fehlende Vertrag auslöst."""
    if a.superadmin:
        return "edit"
    granted = rbac.member_permissions(con, a.email, vg_id)
    return "edit" if rbac.DPA_EDIT in granted else "view" if rbac.DPA_VIEW in granted else None


def _require(con, a, slug, needed="view"):
    vg = _vg(con, slug)
    right = rights(con, a, vg["id"])
    if not right or (needed == "edit" and right != "edit"):
        raise tenancy.Forbidden("Keine Berechtigung für den Vertrag dieser VG.")
    return vg, right


def _require_open(con, a, slug):
    """Recht DPA_EDIT und Vertrag noch offen – einen bestätigten Vertrag ändert nur der Superadmin."""
    vg, right = _require(con, a, slug, "edit")
    if not a.superadmin and status(con, vg["id"])["status"] not in OPEN:
        raise HTTPException(409, "Der Vertrag ist bereits abgeschlossen.")
    return vg, right


def _tenant_names(con, vg_id):
    return [r[0] for r in con.execute("SELECT name FROM tenant WHERE vg_id = ? ORDER BY name", (vg_id,))]


def item(con, a, vg):
    right = rights(con, a, vg["id"])
    d = status(con, vg["id"])
    data = json.loads(d.get("client_data") or "{}")
    result = {
        "slug": vg["slug"], "name": vg["name"], "status": d["status"], "status_label": STATUSES[d["status"]],
        "open": d["status"] in OPEN, "can_edit": right == "edit" and d["status"] in OPEN,
        "fields": [{"key": key, "label": label, "value": data.get(key, "")} for key, label in CLIENT_FIELDS],
        "tenants": _tenant_names(con, vg["id"]), "template_version": d.get("template_version"),
        "generated_hash": d.get("generated_hash"), "signed_on": d.get("signed_on"),
        "document_file": bool(d.get("document_file")), "document_hash": d.get("document_hash"),
        "document_link": d.get("document_link"), "confirmed_by": d.get("confirmed_by"),
        "confirmed_at": d.get("confirmed_at"),
        "processor_missing": [k for k, v in processor().items() if v == MISSING],
    }
    if a.superadmin:
        result["events"] = [dict(r) for r in con.execute(
            "SELECT at, email, action, detail FROM dpa_event WHERE vg_id = ? ORDER BY id DESC", (vg["id"],))]
    return result


# ---------------------------------------------------------------- Schnittstelle
@router.get("/api/dpa")
def list_dpa(a: tenancy.Access = Depends(access)):
    """Verträge der VGs, zu denen der Benutzer gehört (Superadmin: alle)."""
    with tenancy.central() as con:
        vgs = con.execute("SELECT id, slug, name FROM vg ORDER BY name").fetchall()
        return {"items": [item(con, a, vg) for vg in vgs if rights(con, a, vg["id"])],
                "statuses": STATUSES, "superadmin": a.superadmin}


class ClientData(BaseModel):
    client_data: dict


@router.put("/api/dpa/{slug}")
def save_form(slug: str, form: ClientData, a: tenancy.Access = Depends(access)):
    """Angaben des Auftraggebers speichern und den Vertrag dazu erzeugen (Status: ausgefüllt)."""
    with tenancy.central() as con:
        vg, _ = _require_open(con, a, slug)
        data = {key: str(form.client_data.get(key) or "").strip()[:500] for key, _ in CLIENT_FIELDS}
        if not data["client_name"] or not data["client_representative"]:
            raise HTTPException(422, "Bitte mindestens Auftraggeber und vertretungsberechtigte Person angeben.")
        _, checksum = render(data, _tenant_names(con, vg["id"]))
        _save(con, vg["id"], status="draft", client_data=json.dumps(data, ensure_ascii=False),
              template_version=TEMPLATE_VERSION, generated_hash=checksum)
        event(con, vg["id"], a.email, "Vertrag erzeugt", f"Vorlage {TEMPLATE_VERSION}, Prüfsumme {checksum}")
        return item(con, a, vg)


@router.get("/api/dpa/{slug}/document")
def document(slug: str, a: tenancy.Access = Depends(access)):
    """Vertrag zum Drucken bzw. Speichern als PDF."""
    with tenancy.central() as con:
        vg, _ = _require(con, a, slug)
        d = status(con, vg["id"])
        body, checksum = render(json.loads(d.get("client_data") or "{}"), _tenant_names(con, vg["id"]),
                                d.get("template_version") or TEMPLATE_VERSION)
    nonce = secrets.token_urlsafe(16)      # nur das eigene Skript für den Drucken-Knopf darf laufen
    return HTMLResponse(page(body, checksum, f"AVV {vg['name']}", d.get("generated_hash"), nonce),
                        headers={"Content-Security-Policy": f"default-src 'none'; style-src 'unsafe-inline'; "
                                                            f"script-src 'nonce-{nonce}'; base-uri 'none'; "
                                                            f"form-action 'none'; frame-ancestors 'none'"})


@router.post("/api/dpa/{slug}/upload")
def upload(slug: str, file: UploadFile = File(...), a: tenancy.Access = Depends(access)):
    """Unterschriebenen Vertrag als PDF ablegen – nie überschreiben, Prüfsumme speichern."""
    data = file.file.read(MAX_PDF_BYTES + 1)
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(422, "Die Datei ist größer als 10 MB.")
    if not data.startswith(b"%PDF-"):
        raise HTTPException(422, "Bitte den unterschriebenen Vertrag als PDF hochladen.")
    checksum = hashlib.sha256(data).hexdigest()
    with tenancy.central() as con:
        vg, _ = _require_open(con, a, slug)
        folder = os.path.join(db.DATA_DIR, "avv", vg["slug"])
        os.makedirs(folder, exist_ok=True)
        name = f"{dt.datetime.now():%Y%m%d-%H%M%S}-{checksum[:12]}.pdf"
        path = os.path.join(folder, name)
        with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640), "wb") as f:
            f.write(data)
        _save(con, vg["id"], document_file=os.path.join("avv", vg["slug"], name), document_hash=checksum)
        event(con, vg["id"], a.email, "Unterschriebener Vertrag hochgeladen", f"{name}, SHA-256 {checksum}")
        log.info("AVV der VG %s hochgeladen durch %s (%s)", slug, a.email or "lokal", checksum)
        return item(con, a, vg)


class Link(BaseModel):
    link: str


@router.put("/api/dpa/{slug}/link")
def save_link(slug: str, body: Link, a: tenancy.Access = Depends(access)):
    """Link auf die Ablage des unterschriebenen Vertrags bei der VG (DMS, Cloud)."""
    link = body.link.strip()
    if link and not re.fullmatch(r"https?://\S+", link):
        raise HTTPException(422, "Bitte einen Link mit http:// oder https:// angeben.")
    with tenancy.central() as con:
        vg, _ = _require_open(con, a, slug)
        _save(con, vg["id"], document_link=link or None)
        event(con, vg["id"], a.email, "Link zur Ablage" if link else "Link entfernt", link)
        return item(con, a, vg)


@router.get("/api/dpa/{slug}/file")
def signed_file(slug: str, a: tenancy.Access = Depends(access)):
    with tenancy.central() as con:
        vg, _ = _require(con, a, slug, "edit")
        d = status(con, vg["id"])
    if not d.get("document_file"):
        raise HTTPException(404, "Kein Vertrag hochgeladen.")
    return FileResponse(os.path.join(db.DATA_DIR, d["document_file"]), media_type="application/pdf",
                        filename=f"AVV_{vg['slug']}.pdf")


class StatusChange(BaseModel):
    status: str
    signed_on: str = ""
    note: str = ""


@router.post("/api/dpa/{slug}/status")
def change_status(slug: str, change: StatusChange, a: tenancy.Access = Depends(access)):
    """Nur Superadmin: AVV bestätigen (signed), zurücknehmen, als nicht erforderlich markieren."""
    if not a.superadmin:
        raise tenancy.Forbidden("Nur der Superadmin bestätigt Verträge.")
    if change.status not in STATUSES:
        raise HTTPException(422, "Unbekannter Status.")
    with tenancy.central() as con:
        vg = _vg(con, slug)
        d = status(con, vg["id"])
        if change.status == "signed":
            if not d.get("generated_hash"):
                raise HTTPException(422, "Zuerst den Vertrag in der App ausfüllen und erzeugen.")
            if not (d.get("document_file") or d.get("document_link")):
                raise HTTPException(422, "Zuerst den unterschriebenen Vertrag hochladen oder den Link zur Ablage angeben.")
            try:
                signed_on = dt.date.fromisoformat(change.signed_on).isoformat()
            except ValueError:
                raise HTTPException(422, "Bitte das Datum der Unterschrift angeben.")
            _save(con, vg["id"], signed_on=signed_on, confirmed_by=a.email or "lokal",
                  confirmed_at=dt.datetime.now().isoformat(timespec="seconds"))
        set_status(con, vg["id"], change.status, a.email, change.note.strip())
        log.warning("AVV der VG %s: Status %s durch %s", slug, change.status, a.email or "lokal")
        return item(con, a, vg)
