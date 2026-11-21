# -*- coding: utf-8 -*-
"""Übungsdienste: Liste, Erfassen, Ändern und Löschen (der Personenstamm wird unter Einstellungen → Personen gepflegt).
Rechte: TRAININGS (sehen), TRAININGS_EDIT (ändern); immer nur die ausgewählte Wehr."""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import tenancy, trainings
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
    member_ids: List[int] = Field(default_factory=list, max_length=500)
    new_members: List[NewMember] = Field(default_factory=list, max_length=50)
    revision: Optional[int] = Field(default=None, ge=0, strict=True)


def _fields(body):
    return body.model_dump(include={"topic", "started_at", "ended_at", *trainings.OPTIONAL})


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
        rows = trainings.load(con, year=year)
        return {"year": year, "years": years, "trainings": rows, "summary": trainings.summary(rows),
                "members": trainings.directory(con)}


@router.post("/api/trainings")
def api_create_training(body: TrainingIn, a: tenancy.Access = Depends(access)):
    with a.current(TRAININGS_EDIT).connection() as con:
        training_id = _errors(lambda: trainings.create(con, _fields(body), body.member_ids,
                                                       [m.model_dump() for m in body.new_members]))
        return trainings.load(con, training_id=training_id)[0]


@router.put("/api/trainings/{training_id}")
def api_update_training(training_id: int, body: TrainingIn, a: tenancy.Access = Depends(access)):
    if body.revision is None:
        raise HTTPException(428, "Zum Ändern ist die aktuelle Revision der Übung erforderlich.")
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.update(con, training_id, _fields(body), body.revision, body.member_ids,
                                         [m.model_dump() for m in body.new_members]))
        return trainings.load(con, training_id=training_id)[0]


@router.delete("/api/trainings/{training_id}")
def api_delete_training(training_id: int, revision: Optional[int] = None, a: tenancy.Access = Depends(access)):
    if revision is None:
        raise HTTPException(428, "Zum Löschen ist die aktuelle Revision der Übung erforderlich.")
    with a.current(TRAININGS_EDIT).connection() as con:
        _errors(lambda: trainings.delete(con, training_id, revision))
    return {"ok": True}

