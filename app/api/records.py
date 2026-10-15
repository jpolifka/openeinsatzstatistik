# -*- coding: utf-8 -*-
"""Prüfprotokoll und Kostenersatz der VG (Recht VG_RECORDS).
"""
import datetime as dt
from typing import List, Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from app import fees, records, tenancy
from app.rbac import VG_RECORDS

from fastapi import APIRouter
from app.api.common import access, latest_year
router = APIRouter()


# ---------------------------------------------------------------- Prüfprotokoll (Recht VG_RECORDS)
def _managed_vg(a):
    """VG der Gesamtansicht mit Recht auf das Prüfprotokoll -> (vg_id, alle Wehren der VG)."""
    tenants = a.selection if a.vg else []
    if not tenants or not a.vg_can(tenants[0].vg_id, VG_RECORDS):
        raise tenancy.Forbidden("Das Prüfprotokoll gibt es in der Gesamtansicht der VG – mit Recht darauf.")
    vg_id = tenants[0].vg_id
    return vg_id, tenancy.vg_tenants(vg_id)


@router.get("/api/records")
def api_records(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    vg_id, tenants = _managed_vg(a)
    year = year or latest_year(tenants) or dt.date.today().year
    with tenancy.central() as con:
        return {"year": year, "records": records.protocol(con, vg_id, year, tenants)}


class Review(BaseModel):
    done: bool = True


@router.post("/api/records/review-all")
def api_review_all(year: Optional[int] = None, a: tenancy.Access = Depends(access)):
    """Alle offenen Befunde des Jahres bestätigen."""
    vg_id, tenants = _managed_vg(a)
    year = year or latest_year(tenants) or dt.date.today().year
    with tenancy.central() as con:
        return {"ok": True, "reviewed": records.review_all(con, vg_id, year, tenants, a.email)}


@router.post("/api/records/{bks_record_id}/review")
def api_review_record(bks_record_id: str, review: Review, a: tenancy.Access = Depends(access)):
    vg_id, tenants = _managed_vg(a)
    with tenancy.central() as con:
        records.review(con, vg_id, bks_record_id, tenants, a.email, review.done)
        entry = records.check(con, vg_id, bks_record_id, tenants)
    return {"ok": True, "findings": len(entry["findings"])}


# ---------------------------------------------------------------- Kostenersatz (Recht VG_RECORDS)
class Expense(BaseModel):
    label: str = Field(default="", max_length=200)
    amount: float = Field(default=0, ge=0, le=10_000_000, allow_inf_nan=False)


class FeeRequest(BaseModel):
    schedule_id: Optional[int] = None
    bma_cap: Optional[bool] = None     # None: bei Stichwort Brandmeldeanlage höchstens die Pauschale
    expenses: List[Expense] = Field(default=[], max_length=50)
    vat_percent: float = Field(default=0, allow_inf_nan=False)


@router.post("/api/records/{bks_record_id}/fees")
def api_fees(bks_record_id: str, request: FeeRequest, a: tenancy.Access = Depends(access)):
    """Kostenaufstellung nach der Gebührenordnung der VG – nur berechnet, nicht gespeichert."""
    vg_id, tenants = _managed_vg(a)
    if not 0 <= request.vat_percent <= 100 or any(e.amount < 0 for e in request.expenses):
        raise HTTPException(422, "Auslagen und Umsatzsteuer dürfen nicht negativ sein.")
    with tenancy.central() as con:
        try:
            result = fees.calculate(con, vg_id, bks_record_id, tenants, request.schedule_id, request.bma_cap,
                                    [e.model_dump() for e in request.expenses], request.vat_percent)
        except ValueError as e:
            raise HTTPException(422, str(e))
        result["schedules"] = [{"id": s["id"], "name": s["name"], "valid_from": s["valid_from"]}
                               for s in fees.schedules(con, vg_id)]
    return result


