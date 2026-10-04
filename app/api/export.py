# -*- coding: utf-8 -*-
"""Export: Einsatzübersicht als Excel, Zusammenfassung.
"""
import datetime as dt
import io
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.responses import StreamingResponse

from app import excel_export, metrics, store, tenancy, tenant_config
from app.rbac import EXPORT, PEOPLE, STATS

from fastapi import APIRouter
from app.api.common import PLAN_KEYS, XLSX, access, filtered, latest_year, names_for, plan_visible, without_plan
from app.api.evaluation import evaluate
router = APIRouter()


# ---------------------------------------------------------------- Export
def _xlsx(write, name):
    buffer = io.BytesIO()
    write(buffer)
    buffer.seek(0)
    name = f"{name}_{dt.datetime.now():%Y-%m-%d_%H%M}.xlsx"
    return StreamingResponse(buffer, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{name}"'})


def _summary(tenants, year, limit):
    """Kennzahlzeilen je Wehr, Summenzeile und Hinweise für die Excel-Übersicht."""
    parts, _ = evaluate(tenants, year, limit)
    rows = [without_plan({"name": t.name, **metrics.summary(evaluated, limit, t.config)}, plan_visible(t))
            for t, evaluated, _ in parts]
    everything = [e for _, evaluated, _ in parts for e in evaluated]
    combined = tenant_config.combine("Summe", [t.config for t in tenants])
    total = {**metrics.summary(everything, limit, combined), "name": "Summe (Beteiligungen)"}
    # Bedarfsplan in der Summe nur über die Wehren, für die er sichtbar ist
    visible = [t for t in tenants if plan_visible(t)]
    if len(visible) < len(tenants):
        shown = [e for t, evaluated, _ in parts if plan_visible(t) for e in evaluated]
        plan = metrics.summary(shown, limit, tenant_config.combine("Summe", [t.config for t in visible])) \
            if visible else {}
        total.update({key: plan.get(key) for key in PLAN_KEYS})
    notes = []
    if len(tenants) > 1:
        unique, without = metrics.unique_incidents([i for i, _ in everything])
        notes.append(f"Einsätze ohne Doppelte (gleiche Einsatznummer der Leitstelle = ein Einsatz): {unique}")
        if without:
            notes.append(f"{without} Einsätze ohne Einsatznummer der Leitstelle zählen einzeln.")
    return parts, rows, total, notes


@router.get("/api/export")
def api_export(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Excel im Format der Einsatzübersicht (Spalten je Fahrzeug + Anwesenheit). In der Gesamtansicht
    eine Mappe mit Übersicht und je Wehr Einsatzübersicht und Anwesenheit."""
    tenants = a.selection_with(EXPORT)
    year = year or latest_year(tenants)
    if len(tenants) == 1 and not a.vg:
        tenant = tenants[0]
        with tenant.connection() as con:
            incidents = names_for(tenant, store.load_incidents(con, year=year))
            members = store.members_of_year(con, year) if tenant.can(PEOPLE) else None
        if not incidents:
            raise HTTPException(404, "Keine Einsätze für den Export.")
        return _xlsx(lambda target: excel_export.write_workbook(incidents, members, year, target, tenant.config),
                     f"Einsaetze_{tenant.slug}_{year}")
    limit = tenants[0].config.default_limit
    parts, rows, total, notes = _summary(tenants, year, limit)
    workbook_parts = []
    for t, evaluated, _ in parts:
        with t.connection() as con:
            workbook_parts.append((t.config, names_for(t, [i for i, _ in evaluated]),
                                   store.members_of_year(con, year) if t.can(PEOPLE) else None))
    if not any(incidents for _, incidents, _ in workbook_parts):
        raise HTTPException(404, "Keine Einsätze für den Export.")
    return _xlsx(lambda target: excel_export.write_combined_workbook(workbook_parts, rows, total, year, limit, target,
                                                                     notes), f"Einsaetze_{a.vg}_{year}")


@router.get("/api/export/summary")
def api_export_summary(year: Optional[int] = None, limit: Optional[int] = None,
                       tenants: Optional[str] = None, a: tenancy.Access = Depends(access)):
    """Kennzahlen je Wehr als Excel – ohne Namen, daher auch für Rollen nur mit Statistik."""
    tenants = filtered(a.selection_with(STATS), tenants)
    year = year or latest_year(tenants)
    limit = limit if limit is not None else tenants[0].config.default_limit
    if limit not in {value for t in tenants for value in t.config.response_limits}:
        raise HTTPException(422, "Unbekannte Zeitgrenze.")
    _, rows, total, notes = _summary(tenants, year, limit)
    return _xlsx(lambda target: excel_export.write_summary_workbook(rows, total, year, limit, target, notes),
                 f"Kennzahlen_{a.vg or tenants[0].slug}_{year}")

