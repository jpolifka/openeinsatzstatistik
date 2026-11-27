# -*- coding: utf-8 -*-
"""Übungsdienste: Liste, Erfassen, Ändern und Löschen (der Personenstamm wird unter Einstellungen → Personen gepflegt).
Rechte: TRAININGS (sehen), TRAININGS_EDIT (ändern); immer nur die ausgewählte Wehr."""
import io
from typing import List, Optional

import segno
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from app import checkin, tenancy, trainings
from app.api.common import access
from app.rbac import TRAININGS, TRAININGS_EDIT

router = APIRouter()


class NewMember(BaseModel):
    last_name: str = Field(max_length=60)
    first_name: str = Field(default="", max_length=60)


class TrainingIn(BaseModel):
    topic: str = Field(max_length=trainings.LIMITS["topic"])
    started_at: str = Field(max_length=25)
    ended_at: str = Field(max_length=25)
    trainer: Optional[str] = Field(default=None, max_length=trainings.LIMITS["trainer"])
    place: Optional[str] = Field(default=None, max_length=trainings.LIMITS["place"])
    category: Optional[str] = Field(default=None, max_length=trainings.LIMITS["category"])
    notes: Optional[str] = Field(default=None, max_length=trainings.LIMITS["notes"])
    csa_load: bool = False
    member_ids: List[int] = Field(default_factory=list, max_length=500)
    new_members: List[NewMember] = Field(default_factory=list, max_length=50)
    revision: Optional[int] = Field(default=None, ge=0, strict=True)


def _fields(body):
    return body.model_dump(include={"topic", "started_at", "ended_at", "csa_load", *trainings.OPTIONAL})


def _errors(action):
    try:
        return action()
    except KeyError:
        raise HTTPException(404, "Übung nicht gefunden.")
    except trainings.Stale as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/api/trainings")
def api_trainings(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    tenant = a.current(TRAININGS)
    with tenant.connection() as con:
        years = trainings.years(con)
        year = year or years[0]
        rows = trainings.load(con, year=year, with_checkin=tenant.can(TRAININGS_EDIT))
        return {"year": year, "years": years, "trainings": rows, "summary": trainings.summary(rows),
                "members": trainings.directory(con), "csa": trainings.csa_status(con, year)}


@router.get("/api/trainings/checkin")
def api_checkin_link(request: Request, a: tenancy.Access = Depends(access)):
    """Link des QR-Codes zur Anmeldung ohne Benutzerkonto."""
    return {"url": checkin.link_for(a.current(TRAININGS_EDIT), str(request.base_url))}


@router.get("/api/trainings/checkin.svg")
def api_checkin_qr(request: Request, a: tenancy.Access = Depends(access)):
    link = checkin.link_for(a.current(TRAININGS_EDIT), str(request.base_url))
    out = io.BytesIO()      # eigenständiges SVG (mit xmlns), sonst zeigt <img> es nicht an
    segno.make(link, error="m", micro=False).save(out, kind="svg", scale=8, border=2, dark="#000", light="#fff",
                                                  xmldecl=True, svgns=True)
    return Response(out.getvalue(), media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.post("/api/trainings/checkin/rotate")
def api_checkin_rotate(request: Request, a: tenancy.Access = Depends(access)):
    """Neuen Code erzeugen: bisherige Aushänge werden ungültig."""
    tenant = a.current(TRAININGS_EDIT)
    checkin.rotate(tenant)
    return {"url": checkin.link_for(tenant, str(request.base_url))}


@router.post("/api/trainings")
def api_create_training(body: TrainingIn, a: tenancy.Access = Depends(access)):
    with a.current(TRAININGS_EDIT).connection() as con:
        training_id = _errors(lambda: trainings.create(con, _fields(body), body.member_ids,
                                                       [m.model_dump() for m in body.new_members]))
        return trainings.load(con, training_id=training_id, with_checkin=True)[0]


@router.put("/api/trainings/{training_id}")
def api_update_training(training_id: int, body: TrainingIn, a: tenancy.Access = Depends(access)):
    if body.revision is None:
        raise HTTPException(428, "Zum Ändern ist die aktuelle Revision der Übung erforderlich.")
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.update(con, training_id, _fields(body), body.revision, body.member_ids,
                                         [m.model_dump() for m in body.new_members]))
        return trainings.load(con, training_id=training_id, with_checkin=True)[0]


@router.post("/api/trainings/{training_id}/checkin-pin")
def api_new_pin(training_id: int, a: tenancy.Access = Depends(access)):
    """Neue Anmelde-PIN der Übung (die bisherige gilt nicht mehr)."""
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.new_pin(con, training_id))
        return trainings.load(con, training_id=training_id, with_checkin=True)[0]


@router.post("/api/trainings/{training_id}/checkins/accept")
@router.post("/api/trainings/{training_id}/checkins/{checkin_id}/accept")
def api_accept_checkins(training_id: int, checkin_id: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Wartende QR-Anmeldungen bestätigen (eine oder alle): erst jetzt entstehen Person und Teilnahme."""
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.accept_checkins(con, training_id, checkin_id))
        return trainings.load(con, training_id=training_id, with_checkin=True)[0]


@router.delete("/api/trainings/{training_id}/checkins/{checkin_id}")
def api_reject_checkin(training_id: int, checkin_id: int, a: tenancy.Access = Depends(access)):
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.reject_checkin(con, training_id, checkin_id))
        return trainings.load(con, training_id=training_id, with_checkin=True)[0]


@router.delete("/api/trainings/{training_id}")
def api_delete_training(training_id: int, revision: Optional[int] = None, a: tenancy.Access = Depends(access)):
    if revision is None:
        raise HTTPException(428, "Zum Löschen ist die aktuelle Revision der Übung erforderlich.")
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.delete(con, training_id, revision))
    return {"ok": True}

