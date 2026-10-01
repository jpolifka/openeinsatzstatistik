# -*- coding: utf-8 -*-
import datetime as dt

import pytest

from app import metrics
from conftest import make_incident, vehicle


def test_incident_metrics_like_excel_formulas():
    incident = make_incident(station_staff=2, people=[{"id": 1, "name": "Muster, Max"}] * 4, vehicles={
        "02/45": vehicle("02/45", 6, "10:03:00", "10:07:00"),
        "02/24": vehicle("02/24", 3, "10:05:00", "10:09:30"),
        "01/10": vehicle("01/10", 2, "10:06:00", "10:14:00"),
    })
    m = metrics.incident_metrics(incident, 8)
    assert m["daytime"] is True
    assert m["duration_min"] == 60
    assert m["turnout_min"] == 3 and m["arrival_min"] == 7
    assert m["on_time"] is True
    assert m["crew_on_arrival"] == 6            # AR: erstes Fahrzeug
    assert m["crew_within_limit"] == 0          # AS: 7 < t <= 8
    assert m["crew_within_second"] == 5         # AT: 8 < t <= 15
    assert m["crew_plan_total"] == 9            # AU: ohne 01/10
    assert m["crew_total"] == 13                # AM: alle Fahrzeuge + Gerätehaus
    assert metrics.incident_metrics(incident, 10)["crew_within_limit"] == 3


def test_minutes_wrap_past_midnight():
    incident = make_incident(started_at="2025-03-12T23:58:00", ended_at="2025-03-13T00:30:00",
                             vehicles={"02/45": vehicle("02/45", 6, "00:01:00", "00:05:00")})
    m = metrics.incident_metrics(incident)
    assert (m["turnout_min"], m["arrival_min"]) == (3, 7)
    assert m["daytime"] is False


def test_response_plan_counts_relevant_incidents():
    on_time = make_incident(id=1, vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    late = make_incident(id=2, place="Hammerstein", weekend_or_holiday=1,
                         vehicles={"02/45": vehicle("02/45", 6, None, "10:12:00")})
    without_arrival = make_incident(id=3, vehicles={"02/45": vehicle("02/45", 6)})
    level_one = make_incident(id=4, keyword="B1", vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    elsewhere = make_incident(id=5, place="Linz", vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    plan = metrics.response_plan(metrics.evaluate([on_time, late, without_arrival, level_one, elsewhere], 8), 8)
    assert plan["total"]["count"] == 2
    assert plan["total"]["rate"] == 0.5
    assert plan["without_times"] == 1
    windows = {w["key"]: w["count"] for w in plan["windows"]}
    assert windows == {"weekday_day": 1, "weekday_night": 0, "weekend_day": 1, "weekend_night": 0}


def test_statistics_and_attendance():
    people = [{"id": 1, "name": "Muster, Max"}]
    incidents = [
        make_incident(id=1, keyword="B2", subcode="07", people=people),
        make_incident(id=2, keyword="H1", place="Linz", started_at="2025-03-15T20:00:00",
                      ended_at="2025-03-15T20:30:00", weekend_or_holiday=1, people=people),
    ]
    previous = [make_incident(started_at="2024-01-10T10:00:00"), make_incident(started_at="2024-12-10T10:00:00")]
    s = metrics.statistics(metrics.evaluate(incidents), 2025, previous, today=dt.date(2025, 6, 1))
    assert s["count"] == 2 and s["fire_alarm_systems"] == 1
    assert {c["code"]: c["count"] for c in s["categories"]}["H"] == 1
    assert [l["count"] for l in s["levels"]] == [1, 1, 0, 0]
    assert {a["name"]: a["count"] for a in s["areas"]}["sonstige"] == 1
    assert s["daytime_share"] == 0.5
    assert (s["previous_to_date"], s["previous_total"]) == (1, 2)
    assert s["duration_total_min"] == 90

    a = metrics.attendance_overview(metrics.evaluate(incidents))
    assert a["members"] == [{"id": 1, "name": "Muster, Max", "incidents": 2, "nights": 1, "weekends": 1,
                             "last": "2025-03-15T20:00:00", "hours": 1.5, "rate": 1.0}]


@pytest.mark.parametrize("today, expected", [(dt.date(2024, 2, 29), dt.date(2023, 2, 28)),
                                             (dt.date(2024, 3, 1), dt.date(2023, 3, 1))])
def test_previous_year_cutoff_on_leap_day(today, expected):
    previous = [make_incident(started_at=f"{expected.isoformat()}T10:00:00")]
    s = metrics.statistics([], 2024, previous, today=today)
    assert s["previous_to_date"] == 1


def test_monthly_history_fills_gaps_and_averages():
    counts = {"2024-11": 2, "2025-02": 1, "2025-11": 4}
    history = metrics.monthly_history(counts, today=dt.date(2026, 3, 5))
    assert (history[0]["year"], history[0]["month"]) == (2024, 11)
    assert (history[-1]["year"], history[-1]["month"]) == (2025, 12)  # höchstens bis Ende des letzten Jahres
    assert [h["count"] for h in history[:4]] == [2, 0, 0, 1]
    assert history[10]["average"] is None and history[11]["average"] == round(3 / 12, 2)
    current = metrics.monthly_history({"2026-01": 1}, today=dt.date(2026, 3, 5))
    assert len(current) == 2                                            # bis zum Vormonat …
    current = metrics.monthly_history({"2026-01": 1, "2026-03": 1}, today=dt.date(2026, 3, 5))
    assert len(current) == 3 and current[-1]["running"]                 # … außer der laufende hat schon Einsätze
    assert metrics.monthly_history({}) == []
