# -*- coding: utf-8 -*-
"""Verwaltung: Stichwortkatalog einer Wehr bzw. VG (Pflege, Vorlage, Import).
"""
import csv
import io
import re

from app import parser_worker
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import domain, tenancy
from app.rbac import KEYWORDS

from app.admin.common import _invalid, _managed_vg_id, access, log

router = APIRouter()

KEYWORD_CODE = re.compile(r"[A-Z]\d(\.\d\d)?")
MAX_KEYWORD_FILE = 2 * 1024 * 1024


# ---------------------------------------------------------------- Stichwortkatalog
class KeywordIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    terms: str = ""
    active: bool = True


class _Catalog:
    """Stichwortkatalog einer Wehr (Abweichungen von der VG) oder einer VG (Vorgabe für ihre Wehren)."""

    def __init__(self, tenant=None, vg_id=None):
        self.tenant, self.vg_id = tenant, vg_id

    def entries(self):
        """Wirksamer Katalog [{code, name, terms, active, source}]."""
        if self.tenant:
            layer = self.tenant.layer
            with self.tenant.connection() as con:
                return tenancy.tenant_keywords(con, layer)
        with tenancy.central() as con:
            layer = tenancy.load_vg_layer(con, self.vg_id)
        return [{**k, "source": "vg"} for k in layer.keyword_list]

    def save(self, entries):
        if self.tenant:
            layer = self.tenant.layer
            with self.tenant.connection() as con:
                tenancy.save_tenant_keywords(con, entries, layer)
            tenancy.forget_config(self.tenant.slug)
        else:
            with tenancy.central() as con:
                tenancy.save_vg_keywords(con, self.vg_id, entries)
            tenancy.forget_vg_config(self.vg_id)

    def reset(self):
        """Wehr: alle Abweichungen aufheben; VG: wieder die Vorlage."""
        if self.tenant:
            with self.tenant.connection() as con:
                con.execute("DELETE FROM keyword")
            tenancy.forget_config(self.tenant.slug)
        else:
            with tenancy.central() as con:
                tenancy.save_vg_keywords(con, self.vg_id, None)
            tenancy.forget_vg_config(self.vg_id)

    def json(self):
        entries = self.entries()
        result = {"keywords": entries, "custom": any(k["source"] != "vg" for k in entries),
                  "template_missing": len({c for c, _, _ in domain.KEYWORD_CATALOG} - {k["code"] for k in entries})}
        if self.tenant:
            result["slug"] = self.tenant.slug
        else:                                   # je Stichwort die Wehren, die abweichen
            with tenancy.central() as con:
                result["custom"] = con.execute("SELECT 1 FROM vg_keyword WHERE vg_id = ? LIMIT 1",
                                               (self.vg_id,)).fetchone() is not None
            deviations = {}
            for t in tenancy.vg_tenants(self.vg_id):
                for k in _Catalog(t).entries():
                    if k["source"] != "vg":
                        deviations.setdefault(k["code"], []).append(
                            {"tenant": t.name, "kind": "off" if not k["active"] and k["source"] == "changed"
                             else k["source"]})
            result["deviations"] = deviations
            known = {k["code"] for k in entries}
            result["tenant_only"] = sorted(c for c in deviations if c not in known)
        return result

    def put(self, code, name, terms, active):
        entries = self.entries()
        entry = {"code": code, "name": name, "terms": terms, "active": active}
        if any(k["code"] == code for k in entries):
            entries = [entry if k["code"] == code else k for k in entries]
        else:
            entries.append(entry)
        self.save(entries)

    def delete(self, code):
        """Wehr: eigenes Stichwort löschen, eine Abweichung aufheben bzw. ein Stichwort der VG gilt hier nicht."""
        if self.tenant:
            with self.tenant.connection() as con:
                own = con.execute("DELETE FROM keyword WHERE code = ?", (code,)).rowcount
            if own:
                return tenancy.forget_config(self.tenant.slug)
        self.save([k for k in self.entries() if k["code"] != code])


def _catalog(a, slug):
    return _Catalog(tenant=a.tenant(slug, KEYWORDS))


def _vg_catalog(a, vg_slug):
    return _Catalog(vg_id=_managed_vg_id(a, vg_slug, KEYWORDS))


def _keyword_code(code):
    code = code.strip().upper()
    if not KEYWORD_CODE.fullmatch(code):
        _invalid(f"Stichwort „{code}“: bitte wie B2 oder B2.07 angeben.")
    return code


@router.get("/api/admin/{slug}/keywords")
def get_keywords(slug: str, a: tenancy.Access = Depends(access)):
    return _catalog(a, slug).json()


@router.get("/api/admin/vgs/{vg_slug}/keywords")
def get_vg_keywords(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _vg_catalog(a, vg_slug).json()


@router.put("/api/admin/{slug}/keywords/{code}")
def put_keyword(slug: str, code: str, k: KeywordIn, a: tenancy.Access = Depends(access)):
    catalog = _catalog(a, slug)
    catalog.put(_keyword_code(code), k.name.strip(), k.terms.strip(), k.active)
    return catalog.json()


@router.put("/api/admin/vgs/{vg_slug}/keywords/{code}")
def put_vg_keyword(vg_slug: str, code: str, k: KeywordIn, a: tenancy.Access = Depends(access)):
    catalog = _vg_catalog(a, vg_slug)
    catalog.put(_keyword_code(code), k.name.strip(), k.terms.strip(), k.active)
    return catalog.json()


@router.delete("/api/admin/{slug}/keywords/{code}")
def delete_keyword(slug: str, code: str, a: tenancy.Access = Depends(access)):
    catalog = _catalog(a, slug)
    catalog.delete(code)
    return catalog.json()


@router.delete("/api/admin/vgs/{vg_slug}/keywords/{code}")
def delete_vg_keyword(vg_slug: str, code: str, a: tenancy.Access = Depends(access)):
    catalog = _vg_catalog(a, vg_slug)
    catalog.delete(code)
    return catalog.json()


def _add_template(catalog):
    """Fehlende Stichworte der Vorlage ergänzen."""
    entries = catalog.entries()
    known = {k["code"] for k in entries}
    catalog.save(entries + [{"code": c, "name": n, "terms": t, "active": True}
                            for c, n, t in domain.KEYWORD_CATALOG if c not in known])
    return catalog.json()


@router.post("/api/admin/{slug}/keywords/template")
def keywords_from_template(slug: str, a: tenancy.Access = Depends(access)):
    return _add_template(_catalog(a, slug))


@router.post("/api/admin/vgs/{vg_slug}/keywords/template")
def vg_keywords_from_template(vg_slug: str, a: tenancy.Access = Depends(access)):
    return _add_template(_vg_catalog(a, vg_slug))


@router.delete("/api/admin/{slug}/keywords")
def reset_keywords(slug: str, a: tenancy.Access = Depends(access)):
    """Alle Abweichungen der Wehr aufheben: wieder der Katalog der VG."""
    catalog = _catalog(a, slug)
    catalog.reset()
    return catalog.json()


@router.delete("/api/admin/vgs/{vg_slug}/keywords")
def reset_vg_keywords(vg_slug: str, a: tenancy.Access = Depends(access)):
    """Katalog der VG verwerfen, wieder die Vorlage verwenden."""
    catalog = _vg_catalog(a, vg_slug)
    catalog.reset()
    return catalog.json()


def read_keyword_file(filename, data):
    """CSV (Semikolon oder Komma) oder XLSX mit den Spalten Stichwort, Bezeichnung, Suchbegriffe -> [(code, name, terms)].
    Eine Kopfzeile wird erkannt und übersprungen."""
    if filename.lower().endswith(".xlsx"):
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".xlsx") as file:
            file.write(data)
            file.flush()
            sheets = parser_worker.read("xlsx", file.name)
        rows = [[str(c) if c is not None else "" for c in row] for row in next(iter(sheets.values()), [])]
    else:
        text = data.decode("utf-8-sig", errors="replace")
        dialect = csv.Sniffer().sniff(text[:2048], delimiters=";,\t") if text.strip() else csv.excel
        rows = list(csv.reader(io.StringIO(text), dialect))
    entries, seen = [], set()
    if len(rows) > 5000:
        _invalid("Der Stichwortkatalog darf höchstens 5000 Zeilen enthalten.")
    for number, row in enumerate(rows, start=1):
        cells = [c.strip() for c in row] + ["", "", ""]
        code = cells[0].upper().replace(" ", "")
        if not code or (number == 1 and not KEYWORD_CODE.fullmatch(code)):
            continue                            # Leerzeile bzw. Kopfzeile
        if not KEYWORD_CODE.fullmatch(code):
            _invalid(f"Zeile {number}: „{cells[0]}“ ist kein Stichwort wie B2 oder B2.07.")
        if not cells[1]:
            _invalid(f"Zeile {number}: Bezeichnung fehlt.")
        if code in seen:
            _invalid(f"Zeile {number}: {code} steht doppelt in der Datei.")
        seen.add(code)
        entries.append((code, cells[1], cells[2]))
    if not entries:
        _invalid("Die Datei enthält keine Stichworte.")
    return entries


def _import_keywords(catalog, mode, file, who):
    """Katalog aus CSV/XLSX: mode=preview zeigt die Änderungen, merge ergänzt/ändert, replace ersetzt."""
    data = file.file.read(MAX_KEYWORD_FILE + 1)
    if len(data) > MAX_KEYWORD_FILE:
        _invalid("Die Datei ist größer als 2 MB.")
    try:
        entries = read_keyword_file(file.filename or "", data)
    except HTTPException:
        raise
    except Exception as e:  # kaputte Datei
        _invalid(f"Die Datei lässt sich nicht lesen ({e or type(e).__name__}).")
    current = {k["code"]: k for k in catalog.entries()}
    incoming = {code: (name, terms) for code, name, terms in entries}
    preview = {
        "new": [c for c in incoming if c not in current],
        "changed": [c for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) != incoming[c]],
        "unchanged": sum(1 for c in incoming if c in current and (current[c]["name"], current[c]["terms"]) == incoming[c]),
        "missing": [c for c in current if c not in incoming],
    }
    if mode == "preview":
        return preview
    rows = [{"code": code, "name": name, "terms": terms, "active": current.get(code, {}).get("active", True)}
            for code, name, terms in entries]
    if mode == "replace":
        catalog.save(rows)
    elif mode == "merge":
        new = {r["code"]: r for r in rows}
        catalog.save([new.pop(k["code"], k) for k in current.values()] + list(new.values()))
    else:
        _invalid("mode: preview, merge oder replace.")
    log.info("Stichwortkatalog %s importiert (%s) durch %s",
             catalog.tenant.slug if catalog.tenant else f"der VG {catalog.vg_id}", mode, who or "lokal")
    return {**preview, **catalog.json()}


@router.post("/api/admin/{slug}/keywords/import")
def import_keywords(slug: str, mode: str = "preview", file: UploadFile = File(...),
                    a: tenancy.Access = Depends(access)):
    return _import_keywords(_catalog(a, slug), mode, file, a.email)


@router.post("/api/admin/vgs/{vg_slug}/keywords/import")
def import_vg_keywords(vg_slug: str, mode: str = "preview", file: UploadFile = File(...),
                       a: tenancy.Access = Depends(access)):
    return _import_keywords(_vg_catalog(a, vg_slug), mode, file, a.email)


