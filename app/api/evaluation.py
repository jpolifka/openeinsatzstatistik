# -*- coding: utf-8 -*-
"""Auswertung: Jahre und Kennzahlen.
"""
import datetime as dt
from typing import Optional

from fastapi import Depends, HTTPException

from app import metrics, store, tenancy
from app.rbac import PEOPLE, STATS

from fastapi import APIRouter
from app.api.common import access, filtered, latest_year, plan_visible, selection_config, without_plan
router = APIRouter()


# ---------------------------------------------------------------- Auswertung
@router.get("/api/years")
def api_years(a: tenancy.Access = Depends(access)):
    counts = {}
    for t in a.selection_with(STATS):
        with t.connection() as con:
            for row in store.years(con):
                entry = counts.setdefault(row["year"], {"year": row["year"], "count": 0, "last_number": None})
                entry["count"] += row["count"]
                entry["last_number"] = row["last_number"] if len(a.selection) == 1 else None
    return {"years": [counts[y] for y in sorted(counts)], "today": dt.date.today().isoformat()}


def evaluate(tenants, year, limit):
    """Einsätze des Jahres und des Vorjahres je Wehr, jeweils mit der eigenen Konfiguration ausgewertet."""
    parts, months = [], {}
    for t in tenants:
        cfg = t.config
        with t.connection() as con:
            current = metrics.evaluate(store.load_incidents(con, year=year), cfg, limit)
            previous = store.load_incidents(con, year=year - 1)
            for month, count in store.incident_months(con).items():
                months[month] = months.get(month, 0) + count
        parts.append((t, current, previous))
    return parts, months




@router.get("/api/evaluation")
def api_evaluation(year: Optional[int] = None, limit: Optional[int] = None, tenants: Optional[str] = None,
                   a: tenancy.Access = Depends(access)):
    """Auswertung der Auswahl – einer Wehr oder (summiert) mehrerer Wehren einer VG.

    Ohne Recht auf Einsätze/Personal kommt die Anwesenheit (Namen) nicht mit; in der
    Gesamtansicht gibt es sie nie (Kameraden gehören zu einer Wehr).
    """
    selection = filtered(a.selection_with(STATS), tenants)
    cfg = selection_config(selection, a)
    limit = limit or cfg.default_limit
    if limit not in cfg.response_limits:
        allowed = " oder ".join(str(x) for x in cfg.response_limits)
        raise HTTPException(400, f"Die Zeitgrenze muss {allowed} Minuten sein.")
    year = year or latest_year(selection)
    parts, months = evaluate(selection, year, limit)
    current = [e for _, evaluated, _ in parts for e in evaluated]
    previous = [i for _, _, prev in parts for i in prev]
    previous_evaluated = [e for t, _, prev in parts for e in metrics.evaluate(prev, t.config, limit)]
    single = len(selection) == 1 and not a.vg
    # Bedarfsplan nur aus Wehren, für die er sichtbar ist (Freigabe oder Recht PLAN_VIEW)
    plan_parts = [(t, evaluated, prev) for t, evaluated, prev in parts if plan_visible(t)]
    plan_cfg = selection_config([t for t, _, _ in plan_parts], a) if plan_parts else None
    plan_current = [e for _, evaluated, _ in plan_parts for e in evaluated]
    plan_previous = [e for t, _, prev in plan_parts for e in metrics.evaluate(prev, t.config, limit)]
    result = {"year": year,
              "history": metrics.monthly_history(months),
              "statistics": metrics.statistics(current, year, cfg, previous or None),
              "response_plan": metrics.response_plan(plan_current, limit, plan_cfg) if plan_parts else None,
              "response_plan_previous": metrics.response_plan(plan_previous, limit, plan_cfg)
              if plan_parts and any(prev for _, _, prev in plan_parts) else None,
              "response_plan_public": all(t.config.response_plan_public for t in selection),
              "response_plan_hidden": [t.name for t in selection if not plan_visible(t)],
              "attendance": metrics.attendance_overview(current) if single and selection[0].can(PEOPLE) else None,
              # Zeiten und Kräfte wie der Bedarfsplan nur aus Wehren, für die er sichtbar ist
              "timing": metrics.timing(plan_current, plan_cfg, tuple(sorted({*metrics.BUILD_UP_MARKS, limit, plan_cfg.second_limit})))
              if plan_parts else None,
              "workload": metrics.workload(current, metrics.combine_overlaps([metrics.overlaps(e) for _, e, _ in parts])),
              "coverage": metrics.coverage(current),
              "tenants": None}
    if not single:
        unique, without = metrics.unique_incidents([i for i, _ in current])
        result["tenants"] = {
            "participations": len(current), "unique": unique, "without_dispatch_number": without,
            "rows": [without_plan({"slug": t.slug, "name": t.name, **metrics.summary(evaluated, limit, t.config)},
                                   plan_visible(t)) for t, evaluated, _ in parts]}
    return result


