# -*- coding: utf-8 -*-
"""Atemschutz-Dokumentation: Endpunkte der eigenen Ansicht (`/api/atemschutz/me/…`) und die Auswertung der Wehrführung.

Kein Endpunkt nimmt eine Personen-ID entgegen. Die Person ergibt sich allein aus der angemeldeten E-Mail
(`atemschutz.member_for`) in der einen ausgewählten Wehr; Eintrags-IDs gelten nur bei dieser Person (sonst 404).
"""
import datetime as dt
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app import atemschutz, mail, tenancy
from app.api.common import access
from app.rbac import AGT_EVAL, AGT_OWN

router = APIRouter()


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")        # keine unbekannten Felder (insbesondere keine member_id)


class Source(_In):
    kind: str = Field(max_length=20)
    id: int


class EntryIn(_In):
    kind: Optional[str] = Field(default=None, max_length=20)
    started_at: Optional[str] = Field(default=None, max_length=25)
    duration_min: Optional[int] = Field(default=None, strict=True)
    place: Optional[str] = Field(default=None, max_length=atemschutz.LIMITS["place"])
    keyword: Optional[str] = Field(default=None, max_length=atemschutz.LIMITS["keyword"])
    start_bar: Optional[int] = Field(default=None, strict=True)
    end_bar: Optional[int] = Field(default=None, strict=True)
    external: bool = False
    organisation: Optional[str] = Field(default=None, max_length=atemschutz.LIMITS["organisation"])
    notes: Optional[str] = Field(default=None, max_length=atemschutz.LIMITS["notes"])
    source: Optional[Source] = None
    revision: Optional[int] = Field(default=None, ge=0, strict=True)


class MedicalIn(_In):
    examined_on: str = Field(max_length=10)
    valid_until: str = Field(max_length=10)


class ReminderIn(_In):
    offsets: List[int] = Field(default_factory=list, max_length=3)


def _handle(action):
    try:
        return action()
    except atemschutz.NotFound:
        raise HTTPException(404, "Nicht gefunden.")
    except atemschutz.Stale as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


def _own(a, con):
    """Die eigene Person in der ausgewählten Wehr; ohne Eintrag im Personalstamm gibt es keine Daten."""
    member_id = atemschutz.member_for(con, a.email)
    if member_id is None:
        raise HTTPException(404, "Deine E-Mail-Adresse ist im Personalstamm dieser Wehr nicht hinterlegt.")
    return atemschutz.Own(con, member_id, a.email)


@router.get("/api/atemschutz/me")
def api_me(year: Optional[int] = Query(None, ge=2000, le=2100), a: tenancy.Access = Depends(access)):
    tenant = a.current(AGT_OWN)
    with tenant.connection() as con:
        member_id = atemschutz.member_for(con, a.email)
        if member_id is None:
            return {"linked": False}
        own = atemschutz.Own(con, member_id, a.email)
        year = year or dt.date.today().year
        return {"linked": True, "year": year, "years": own.years(), "entries": own.entries(year),
                "totals": own.totals(year), "medical": own.medical(), "reminder": own.reminder(),
                "reminder_days": list(atemschutz.REMINDER_DAYS), "admin_access": own.admin_access(), "mail": mail.enabled(),
                "kinds": atemschutz.KINDS, "bar_max": atemschutz.MAX_BAR,
                "name": con.execute("SELECT name FROM member WHERE id = ?", (member_id,)).fetchone()["name"]}


@router.get("/api/atemschutz/me/candidates")
def api_candidates(year: Optional[int] = Query(None, ge=2000, le=2100), a: tenancy.Access = Depends(access)):
    with a.current(AGT_OWN).connection() as con:
        return {"candidates": _own(a, con).candidates(year or dt.date.today().year)}


@router.post("/api/atemschutz/me/entries")
def api_create_entry(body: EntryIn, a: tenancy.Access = Depends(access)):
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        source = (body.source.kind, body.source.id) if body.source else None
        return _handle(lambda: own.create(body.model_dump(exclude={"source", "revision"}), source))


@router.put("/api/atemschutz/me/entries/{entry_id}")
def api_update_entry(entry_id: int, body: EntryIn, a: tenancy.Access = Depends(access)):
    if body.revision is None:
        raise HTTPException(428, "Zum Ändern ist die aktuelle Revision des Eintrags erforderlich.")
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        return _handle(lambda: own.update(entry_id, body.revision, body.model_dump(exclude={"source", "revision"})))


@router.delete("/api/atemschutz/me/entries/{entry_id}")
def api_delete_entry(entry_id: int, revision: Optional[int] = None, a: tenancy.Access = Depends(access)):
    if revision is None:
        raise HTTPException(428, "Zum Löschen ist die aktuelle Revision des Eintrags erforderlich.")
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        _handle(lambda: own.delete(entry_id, revision))
    return {"ok": True}


@router.post("/api/atemschutz/me/medical")
def api_add_medical(body: MedicalIn, a: tenancy.Access = Depends(access)):
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        return {"medical": _handle(lambda: own.add_medical(body.examined_on, body.valid_until))}


@router.delete("/api/atemschutz/me/medical/{medical_id}")
def api_delete_medical(medical_id: int, a: tenancy.Access = Depends(access)):
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        return {"medical": _handle(lambda: own.delete_medical(medical_id))}


@router.put("/api/atemschutz/me/reminder")
def api_set_reminder(body: ReminderIn, a: tenancy.Access = Depends(access)):
    if body.offsets and not mail.enabled():
        raise HTTPException(422, "Auf diesem Server ist kein Mailversand eingerichtet.")
    with a.current(AGT_OWN).connection() as con:
        own = _own(a, con)
        return {"reminder": _handle(lambda: own.set_reminder(body.offsets))}


@router.get("/api/atemschutz/summary")
def api_summary(year: Optional[int] = Query(None, ge=2000, le=2100), a: tenancy.Access = Depends(access)):
    """Auswertung der Wehrführung: je Person nur Summen (keine Einzeleinträge, Drücke, Orte oder Notizen)."""
    tenant = a.current(AGT_EVAL)
    year = year or dt.date.today().year
    with tenant.connection() as con:
        atemschutz.audit(con, a.email, "agt.summary.view")
        return {"year": year, "years": atemschutz.summary_years(con), "people": atemschutz.summary(con, year),
                "kinds": atemschutz.KINDS}


class CosignIn(_In):
    revision: int = Field(ge=0, strict=True)


@router.get("/api/atemschutz/cosign")
def api_cosign_list(year: Optional[int] = Query(None, ge=2000, le=2100), a: tenancy.Access = Depends(access)):
    """Einträge zum Abzeichnen (Wehrführung und Stellvertretung): Einzeleinträge ohne Notizen; jeder Abruf wird protokolliert."""
    tenant = a.current(AGT_EVAL)
    year = year or dt.date.today().year
    with tenant.connection() as con:
        atemschutz.audit(con, a.email, "agt.cosign.view")
        return {"year": year, "years": atemschutz.summary_years(con), "entries": atemschutz.cosign_list(con, year),
                "kinds": atemschutz.KINDS}


@router.post("/api/atemschutz/cosign/{entry_id}")
def api_cosign(entry_id: int, body: CosignIn, a: tenancy.Access = Depends(access)):
    with a.current(AGT_EVAL).connection() as con:
        _handle(lambda: atemschutz.cosign(con, entry_id, body.revision, a.email))
        return {"ok": True}


@router.delete("/api/atemschutz/cosign/{entry_id}")
def api_uncosign(entry_id: int, a: tenancy.Access = Depends(access)):
    with a.current(AGT_EVAL).connection() as con:
        _handle(lambda: atemschutz.uncosign(con, entry_id, a.email))
        return {"ok": True}
