# -*- coding: utf-8 -*-
"""Gemeinsames der Verwaltung: Zugriff, Protokoll und Fehlermeldungen."""
import logging

from fastapi import HTTPException

from app import auth, tenancy
from app.rbac import VG_FEES

log = logging.getLogger("pdf2einsatz")

access = auth.access


def _invalid(message):
    raise HTTPException(422, message)


def _managed_vg_id(a, vg_slug, permission=VG_FEES):
    """VG, in der der Benutzer das Recht auf Ebene der VG hat (Gebührenordnung, Vorgaben für die Wehren)."""
    with tenancy.central() as con:
        row = con.execute("SELECT id FROM vg WHERE slug = ?", (vg_slug,)).fetchone()
    if not row or not a.vg_can(row["id"], permission):
        raise tenancy.Forbidden("Keine Berechtigung für diese VG.")
    return row["id"]
