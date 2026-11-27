# -*- coding: utf-8 -*-
"""Einsätze: Liste, Bearbeiten, Löschen.
"""
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, create_model

from app import store, tenancy
from app.incident_schema import OPTIONAL_COUNTS
from app.rbac import DELETE, INCIDENTS, PEOPLE, PEOPLE_EDIT, WRITE
from app.timeutil import year_of

from fastapi import APIRouter
from app.api.common import access, incident_json, latest_year, log, parse_incident_key
router = APIRouter()


# ---------------------------------------------------------------- Einsätze
MAX_TEXT = 500            # Länge eines Textfelds; Berichtstexte sind deutlich kürzer
MAX_ROWS = 300            # Fahrzeuge bzw. Anwesende je Einsatz

IncidentFields = create_model(
    "IncidentFields",
    **{name: (Optional[int], Field(default=None, ge=0, strict=True)) if name in (*store.INT_FIELDS, *OPTIONAL_COUNTS)
       else (Optional[str], Field(default=None, max_length=MAX_TEXT)) for name in store.FIELDS})


@router.get("/api/incidents")
def api_incidents(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Einsätze der Auswahl; in der Gesamtansicht nur aus Wehren mit Recht auf Einsätze, nach Beginn sortiert."""
    tenants = a.selection_with(INCIDENTS)
    year = year or latest_year(tenants)
    incidents = []
    for tenant in tenants:
        with tenant.connection() as con:
            leaders = store.LeaderNames(con)
            loaded = store.load_incidents(con, year=year)
            incidents += [incident_json(i, leaders, tenant) for i in loaded]
    if len(tenants) > 1:
        incidents.sort(key=lambda i: (i["started_at"] or "", i["tenant"]))
    return {"year": year, "incidents": incidents}


class VehicleEdit(BaseModel):
    call_sign: str = Field(max_length=60)
    crew: Optional[int] = Field(default=None, ge=0, le=99, strict=True)
    departed: Optional[str] = Field(default=None, max_length=20)
    arrived: Optional[str] = Field(default=None, max_length=20)


class PersonEdit(BaseModel):
    id: Optional[int] = None          # vorhandener Kamerad
    name: Optional[str] = Field(default=None, max_length=120)   # sonst „Nachname, Vorname“ (wird bei Bedarf angelegt)
    role: Optional[str] = Field(default=None, max_length=120)
    vehicle: Optional[str] = Field(default=None, max_length=60)


# Einsatz bearbeiten: Felder, dazu optional Fahrzeuge und Anwesenheit (fehlen sie, bleiben sie unverändert)
IncidentUpdate = create_model("IncidentUpdate", __base__=IncidentFields,
                              revision=(Optional[int], Field(default=None, ge=0, strict=True)),
                              vehicles=(Optional[List[VehicleEdit]], Field(default=None, max_length=MAX_ROWS)),
                              people=(Optional[List[PersonEdit]], Field(default=None, max_length=MAX_ROWS)))


@router.put("/api/incidents/{key}")
def api_update_incident(key: str, update: IncidentUpdate, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    tenant = a.tenant(slug, WRITE)
    changes = update.model_dump(exclude_unset=True)
    revision = changes.pop("revision", None)
    if "started_at" in changes and not changes["started_at"]:
        raise HTTPException(422, "Der Einsatzbeginn darf nicht gelöscht werden.")
    vehicles, people = changes.pop("vehicles", None), changes.pop("people", None)
    by_date = tenant.config.numbering == "by_date"
    if by_date:
        changes.pop("number", None)          # ergibt sich aus dem Beginn
    if not tenant.can(PEOPLE):
        changes.pop("unit_leader", None)     # sieht den Einheitsführung nicht (Name), ändert ihn also auch nicht
    if people is not None and not tenant.can(PEOPLE_EDIT):
        raise tenancy.Forbidden("Keine Berechtigung, die Anwesenheit zu bearbeiten.")
    if vehicles is not None and any(v["call_sign"] not in tenant.config.vehicles for v in vehicles):
        raise HTTPException(422, "Unbekanntes Fahrzeug – Fahrzeuge der Wehr in der Verwaltung pflegen.")
    with tenant.connection() as con:
        try:
            current = store.load_incident(con, incident_id)
            if not current:
                raise KeyError(incident_id)
            if revision is None:
                raise HTTPException(428, "Die Einsatzrevision ist erforderlich. Bitte neu laden und erneut speichern.")
            old_year = current["year"]
            new_year = year_of(changes["started_at"]) if changes.get("started_at") else old_year
            if by_date and new_year and new_year != old_year:
                changes["number"] = store.next_number(con, new_year)   # vorläufig ans Ende des neuen Jahres
            store.update_incident(con, incident_id, changes, modified_by=a.email, revision=revision, manual=True)
            if by_date:
                for y in {old_year, store.load_incident(con, incident_id)["year"]} - {None}:
                    store.renumber(con, y)
            if vehicles is not None:
                store.replace_vehicles(con, incident_id, vehicles)
            if people is not None:
                store.replace_attendance(con, incident_id, people)
        except KeyError:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        except store.DuplicateIncident as e:
            raise HTTPException(409, str(e))
        except store.StaleIncident as e:
            raise HTTPException(409, str(e))
        except ValueError as e:
            raise HTTPException(422, str(e))
        return incident_json(store.load_incident(con, incident_id), store.LeaderNames(con), tenant)


@router.get("/api/members")
def api_members(tenant: str, a: tenancy.Access = Depends(access)):
    """Kameraden einer Wehr für Vorschläge beim Bearbeiten der Anwesenheit."""
    with a.tenant(tenant, PEOPLE).connection() as con:
        return {"members": store.all_members(con)}


@router.delete("/api/incidents/{key}")
def api_delete_incident(key: str, revision: Optional[int] = None, a: tenancy.Access = Depends(access)):
    slug, incident_id = parse_incident_key(key)
    tenant = a.tenant(slug, DELETE)
    with tenant.connection() as con:
        current = store.load_incident(con, incident_id)
        if not current:
            raise HTTPException(404, "Einsatz nicht gefunden.")
        if revision is None:
            raise HTTPException(428, "Zum Löschen ist die aktuelle Einsatzrevision erforderlich.")
        if current["revision"] != revision:
            raise HTTPException(409, "Der Einsatz wurde inzwischen geändert. Bitte neu laden und erneut prüfen.")
        year = current["year"]
        try:
            store.delete_incident(con, incident_id, revision=revision)
        except store.StaleIncident as error:
            raise HTTPException(409, str(error))
        if tenant.config.numbering == "by_date":
            store.renumber(con, year)
    log.info("Einsatz %s gelöscht von %s", key, a.email or "lokal")
    return {"ok": True}


