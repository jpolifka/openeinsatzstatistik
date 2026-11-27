# -*- coding: utf-8 -*-
import datetime as dt

import pytest

from app import metrics
from conftest import CFG, make_incident, vehicle


def test_missing_attendance_is_not_a_certified_zero():
    incident = make_incident()
    evaluated = [(incident, metrics.incident_metrics(incident, CFG))]
    assert metrics.staff_totals(evaluated) == {"staff_hours": None, "staff_recorded": 0, "staff_total": 1}


def test_incident_metrics_like_excel_formulas():
    incident = make_incident(station_staff=2, people=[{"id": 1, "name": "Muster, Max"}] * 4, vehicles={
        "02/45": vehicle("02/45", 6, "10:03:00", "10:07:00"),
        "02/24": vehicle("02/24", 3, "10:05:00", "10:09:30"),
        "01/10": vehicle("01/10", 2, "10:06:00", "10:14:00"),
    })
    m = metrics.incident_metrics(incident, CFG, 8)
    assert m["daytime"] is True
    assert m["duration_min"] == 60
    assert m["turnout_min"] == 3 and m["arrival_min"] == 7
    assert m["on_time"] is True
    assert m["crew_on_arrival"] == 6            # AR: erstes Fahrzeug
    assert m["crew_within_limit"] == 0          # AS: 7 < t <= 8
    assert m["crew_within_second"] == 5         # AT: 8 < t <= 15
    assert m["crew_plan_total"] == 9            # AU: ohne 01/10
    assert m["crew_total"] == 13                # AM: alle Fahrzeuge + Gerätehaus
    assert metrics.incident_metrics(incident, CFG, 10)["crew_within_limit"] == 3


def test_minutes_wrap_past_midnight():
    incident = make_incident(started_at="2025-03-12T23:58:00", ended_at="2025-03-13T00:30:00",
                             vehicles={"02/45": vehicle("02/45", 6, "00:01:00", "00:05:00")})
    m = metrics.incident_metrics(incident, CFG)
    assert (m["turnout_min"], m["arrival_min"]) == (3, 7)
    assert m["daytime"] is False


def test_response_plan_counts_relevant_incidents():
    on_time = make_incident(id=1, vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    late = make_incident(id=2, place="Probenhausen", weekend_or_holiday=1,
                         vehicles={"02/45": vehicle("02/45", 6, None, "10:12:00")})
    without_arrival = make_incident(id=3, vehicles={"02/45": vehicle("02/45", 6)})
    level_one = make_incident(id=4, keyword="B1", vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    elsewhere = make_incident(id=5, place="Linz", vehicles={"02/45": vehicle("02/45", 6, None, "10:07:00")})
    plan = metrics.response_plan(metrics.evaluate([on_time, late, without_arrival, level_one, elsewhere], CFG, 8), 8, CFG)
    assert plan["total"]["count"] == 2
    assert plan["total"]["rate"] == 0.5
    assert plan["without_times"] == 1
    windows = {w["key"]: w["count"] for w in plan["windows"]}
    assert windows == {"weekday_day": 1, "weekday_night": 0, "weekend_day": 1, "weekend_night": 0}


def test_aborted_incident_without_arrival_counts_as_on_time():
    aborted = make_incident(id=1, abort_reason="Täuschungsalarm", vehicles={"02/45": vehicle("02/45", 6)})
    arrived_late = make_incident(id=2, abort_reason="in Bereitstellung",
                                 vehicles={"02/45": vehicle("02/45", 6, None, "10:12:00")})
    m = metrics.incident_metrics(aborted, CFG, 8)
    assert (m["arrival_min"], m["on_time"], m["aborted"]) == (None, True, True)
    # mit Eintreffzeit zählt diese, auch bei hinterlegtem Abbruch
    assert metrics.incident_metrics(arrived_late, CFG, 8)["on_time"] is False
    plan = metrics.response_plan(metrics.evaluate([aborted, arrived_late], CFG, 8), 8, CFG)
    assert (plan["total"]["count"], plan["total"]["on_time"], plan["without_times"]) == (2, 1, 0)
    assert plan["total"]["arrival_min"] == 12


def test_statistics_and_attendance():
    people = [{"id": 1, "name": "Muster, Max"}]
    incidents = [
        make_incident(id=1, keyword="B2", subcode="07", people=people),
        make_incident(id=2, keyword="H1", place="Linz", started_at="2025-03-15T20:00:00",
                      ended_at="2025-03-15T20:30:00", weekend_or_holiday=1, people=people),
    ]
    previous = [make_incident(started_at="2024-01-10T10:00:00"), make_incident(started_at="2024-12-10T10:00:00")]
    s = metrics.statistics(metrics.evaluate(incidents, CFG), 2025, CFG, previous, today=dt.date(2025, 6, 1))
    assert s["count"] == 2 and s["fire_alarm_systems"] == 1
    assert {c["code"]: c["count"] for c in s["categories"]}["H"] == 1
    assert [l["count"] for l in s["levels"]] == [1, 1, 0, 0]
    assert {a["name"]: a["count"] for a in s["areas"]}["sonstige"] == 1
    assert s["daytime_share"] == 0.5
    assert (s["previous_to_date"], s["previous_total"]) == (1, 2)
    assert s["duration_total_min"] == 90

    a = metrics.attendance_overview(metrics.evaluate(incidents, CFG))
    assert a["members"] == [{"id": 1, "name": "Muster, Max", "incidents": 2, "nights": 1, "weekends": 1,
                             "last": "2025-03-15T20:00:00", "hours": 1.5, "rate": 1.0,
                                 "functions": {}, "agt_incidents": 0, "agt_minutes": 0}]


@pytest.mark.parametrize("today, expected", [(dt.date(2024, 2, 29), dt.date(2023, 2, 28)),
                                             (dt.date(2024, 3, 1), dt.date(2023, 3, 1))])
def test_previous_year_cutoff_on_leap_day(today, expected):
    previous = [make_incident(started_at=f"{expected.isoformat()}T10:00:00")]
    s = metrics.statistics([], 2024, CFG, previous, today=today)
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


def test_unique_incidents_over_record_and_dispatch_number():
    incidents = [make_incident(bks_record_id="1", dispatch_number="A"),
                 make_incident(bks_record_id="1"),                       # selbst angelegt: ohne Leitstellen-Nr.
                 make_incident(dispatch_number="A"),                     # Altdaten: nur Leitstellen-Nr.
                 make_incident(bks_record_id="2"),
                 make_incident(), make_incident()]
    assert metrics.unique_incidents(incidents) == (4, 2)


# ---------------------------------------------------------------- Zeiten, Kräfte, Belastung
def _timed(**overrides):
    return make_incident(**overrides)


def test_percentile_and_distribution_use_nearest_rank():
    assert metrics.percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 0.9) == 9
    assert metrics.percentile([5], 0.9) == 5
    assert metrics.percentile([], 0.9) is None
    d = metrics.distribution([4, 6, None, 8], 5)
    assert (d["valid"], d["total"], d["median"], d["average"]) == (3, 5, 6, 6)


def test_travel_time_is_per_vehicle_not_first_departure_to_last_arrival():
    incident = make_incident(vehicles={
        "02/45": vehicle("02/45", 6, "10:03:00", "10:07:00"),     # 4 min Anfahrt
        "02/24": vehicle("02/24", 3, "10:05:00", "10:12:00"),     # 7 min Anfahrt
    })
    t = metrics.timing(metrics.evaluate([incident], CFG), CFG)
    assert t["travel"]["valid"] == 2 and t["travel"]["median"] == 5.5
    assert t["turnout"]["median"] == 3 and t["arrival"]["median"] == 7


def test_timing_counts_missing_times_as_not_evaluable():
    with_times = make_incident(id=1, vehicles={"02/45": vehicle("02/45", 6, "10:03:00", "10:07:00")})
    without = make_incident(id=2, vehicles={"02/45": vehicle("02/45", 6)})
    t = metrics.timing(metrics.evaluate([with_times, without], CFG), CFG)
    assert (t["arrival"]["valid"], t["arrival"]["total"]) == (1, 2)
    assert (t["travel"]["valid"], t["travel"]["total"]) == (1, 1)


def test_crew_build_up_after_alarm():
    incident = make_incident(vehicles={
        "02/45": vehicle("02/45", 6, "10:03:00", "10:07:00"),
        "02/24": vehicle("02/24", 3, "10:05:00", "10:12:00"),
    })
    t = metrics.timing(metrics.evaluate([incident], CFG), CFG, (5, 10, 15))
    assert [(b["minutes"], b["crew"]) for b in t["build_up"]] == [(5, 0), (10, 6), (15, 9)]


def test_timing_groups_flag_small_samples():
    incident = make_incident(vehicles={"02/45": vehicle("02/45", 6, "10:03:00", "10:07:00")})
    t = metrics.timing(metrics.evaluate([incident], CFG), CFG)
    assert t["by_area"][0]["count"] == 1 and t["by_area"][0]["small"] is True
    assert {w["key"]: w["count"] for w in t["by_window"]}["weekday_day"] == 1


def test_overlaps_ignore_touching_incidents_and_measure_overlap():
    def at(id, start, end):
        return make_incident(id=id, started_at=f"2025-03-12T{start}", ended_at=f"2025-03-12T{end}")
    evaluated = metrics.evaluate([at(1, "10:00:00", "11:00:00"), at(2, "10:30:00", "11:30:00"),
                                  at(3, "11:30:00", "12:00:00"), at(4, "14:00:00", "15:00:00")], CFG)
    o = metrics.overlaps(evaluated)
    assert (o["valid"], o["incidents_with_overlap"], o["max_concurrent"], o["overlap_minutes"]) == (4, 2, 2, 30)
    assert metrics.combine_overlaps([o, o])["overlap_minutes"] == 60


def test_workload_counts_long_night_and_weekend_incidents():
    long_day = make_incident(id=1, started_at="2025-03-12T10:00:00", ended_at="2025-03-12T13:00:00")
    night = make_incident(id=2, started_at="2025-03-12T23:00:00", ended_at="2025-03-12T23:30:00", weekend_or_holiday=1)
    unknown_end = make_incident(id=3, ended_at=None)
    evaluated = metrics.evaluate([long_day, night, unknown_end], CFG)
    w = metrics.workload(evaluated, metrics.overlaps(evaluated))
    assert (w["long"]["count"], w["night"]["count"], w["weekend"]["count"]) == (1, 1, 1)
    assert w["duration"]["valid"] == 2 and w["duration"]["total"] == 3
    assert sum(b["count"] for b in w["buckets"]) == 2
    assert [(b["from"], b["to"]) for b in w["buckets"]][:2] == [(0, 30), (30, 60)] and w["buckets"][-1]["to"] is None


def test_coverage_reports_available_data():
    complete = make_incident(id=1, people=[{"id": 1, "name": "Muster, Max"}], unit_leader="M. Muster",
                             vehicles={"02/45": vehicle("02/45", 6, "10:03:00", "10:07:00")})
    bare = make_incident(id=2, vehicles={}, unit_leader=None)
    c = metrics.coverage(metrics.evaluate([complete, bare], CFG))
    assert c["total"] == 2 and {r["key"]: r["valid"] for r in c["rows"]} == {
        "duration": 2, "turnout": 1, "arrival": 1, "crew": 1, "attendance": 1, "leader": 1}


# ---------------------------------------------------------------- Abbrüche, Anlagen, Fahrzeuge, Atemschutz, Brand, Rettung
def test_abort_kinds_group_the_free_text():
    from app import domain
    kinds = {text: domain.abort_kind(text) for text in (
        "Täuschungsalarm einer automatischen BMA (DIN VDE 0833-1)", "Böswilliger Alarm", "Technischer Alarm einer BMA",
        "Es konnte kein Schadenereignis festgestellt werden", "in Bereitstellung", "nicht erforderlich",
        "Kräfte der VG nicht mehr erforderlich", "kein Fahrer für das HLF vorhanden war", "", None)}
    assert list(kinds.values()) == ["false_alarm", "false_alarm", "false_alarm", "false_alarm", "standby",
                                    "not_needed", "not_needed", "other", None, None]


def test_aborts_share_and_fire_alarm_systems():
    incidents = [make_incident(id=1, keyword="B2", subcode="07", abort_reason="Täuschungsalarm einer BMA"),
                 make_incident(id=2, keyword="B2", subcode="07"),
                 make_incident(id=3, keyword="H1", subcode="01", abort_reason="in Bereitstellung"),
                 make_incident(id=4, keyword="H1", subcode="01")]
    a = metrics.aborts(metrics.evaluate(incidents, CFG))
    assert (a["total"], a["aborted"], a["share"]) == (4, 2, 0.5)
    assert {k["kind"]: k["count"] for k in a["kinds"]} == {"false_alarm": 1, "not_needed": 0, "standby": 1, "other": 0}
    assert a["fire_alarm_systems"] == {"count": 2, "aborted": 1, "false_alarms": 1, "share": 0.5}
    assert {c["code"]: (c["count"], c["aborted"]) for c in a["categories"]} == {"B": (2, 1), "H": (2, 1)}


def test_alarm_systems_group_by_number_then_object():
    incidents = [
        make_incident(id=1, keyword="B2", subcode="07", alarm_system="301986", building="WH Musterhaus",
                      abort_reason="Täuschungsalarm"),
        make_incident(id=2, keyword="B2", subcode="07", alarm_system="301986", building="WH Musterhaus"),
        make_incident(id=3, keyword="B2", subcode="07", building="HG Beispielhof"),
        make_incident(id=4, keyword="B2", subcode="07"),
        make_incident(id=5, keyword="H1", subcode="01"),
    ]
    result = metrics.alarm_systems(metrics.evaluate(incidents, CFG))
    assert result["total"] == 4 and result["identified"] == 3
    rows = result["rows"]
    assert [(r["system"], r["building"], r["count"], r["false_alarms"], r["known"]) for r in rows] == [
        ("301986", "WH Musterhaus", 2, 1, True), (None, "HG Beispielhof", 1, 0, True), (None, None, 1, 0, False)]
    assert rows[0]["false_share"] == 0.5


def test_vehicle_usage_counts_deployed_and_standby():
    def with_state(call_sign, deployed, crew=4, alerted="10:00:00", departed="10:04:00", finished="11:00:00"):
        return {**vehicle(call_sign, crew, departed, None), "alerted": alerted, "finished": finished, "deployed": deployed}
    incidents = [
        make_incident(id=1, vehicles={"02/45": with_state("02/45", 1), "02/24": with_state("02/24", 0, departed=None)}),
        make_incident(id=2, vehicles={"02/45": with_state("02/45", 1, crew=2, alerted="23:30:00", finished="00:30:00"),
                                      "02/24": with_state("02/24", None)}),
    ]
    rows = {r["call_sign"]: r for r in metrics.vehicle_usage(metrics.evaluate(incidents, CFG), CFG)["rows"]}
    first, second = rows["02/45"], rows["02/24"]
    assert (first["alerted"], first["drove"], first["deployed"], first["standby"]) == (2, 2, 2, 0)
    assert first["hours"] == 2.0 and first["crew_avg"] == 3.0       # 60 min + 60 min über Mitternacht
    assert (second["alerted"], second["drove"], second["standby"], second["unknown"]) == (2, 1, 1, 1)
    assert second["standby_share"] == 1.0 and second["known"] == 1      # „unbekannt“ zählt nicht mit


def test_vehicle_usage_without_finish_time_does_not_fail():
    v = {**vehicle("02/45", 4, "10:04:00", None), "alerted": "10:00:00", "finished": None, "deployed": 1}
    rows = metrics.vehicle_usage(metrics.evaluate([make_incident(id=1, vehicles={"02/45": v})], CFG), CFG)["rows"]
    assert rows[0]["drove"] == 1 and rows[0]["hours"] == 0.0


def test_respiratory_counts_carriers_and_minutes():
    people = [{"id": 1, "name": "Muster, Max", "agt": 1, "agt_min": 20}, {"id": 2, "name": "Beispiel, Erika", "agt": 1, "agt_min": 10},
              {"id": 3, "name": "Probe, Otto", "agt": 0, "agt_min": 0}]
    incidents = [
        make_incident(id=1, vehicles={"02/45": {**vehicle("02/45", 6), "respiratory": 2}}, people=people),
        make_incident(id=2, vehicles={"02/45": {**vehicle("02/45", 6), "respiratory": 0}}),
        make_incident(id=3, vehicles={"02/45": vehicle("02/45", 6)}),          # Altdaten: nicht angegeben
    ]
    r = metrics.respiratory(metrics.evaluate(incidents, CFG))
    assert (r["total"], r["known"], r["with_agt"], r["carriers"]) == (3, 2, 1, 2)
    assert (r["persons"], r["minutes"], r["average_minutes"], r["longest_minutes"]) == (2, 30, 15.0, 20)


def test_fire_course_measures_from_arrival():
    base = dict(keyword="B2", subcode="01", started_at="2025-03-12T10:00:00", ended_at="2025-03-12T12:00:00")
    arrive = {"02/45": vehicle("02/45", 6, "10:03:00", "10:08:00")}
    incidents = [
        make_incident(id=1, **base, vehicles=arrive, tactic="Innenangriff", fire_controlled_at="2025-03-12T10:28:00",
                      fire_out_at="2025-03-12T10:58:00", fire_watch_until="2025-03-12T12:58:00"),
        make_incident(id=2, **base, vehicles=arrive),                                  # ohne Angaben
        make_incident(id=3, **base, vehicles=arrive, abort_reason="nicht erforderlich"),   # Abbruch: zählt nicht
        make_incident(id=4, keyword="B2", subcode="07", vehicles=arrive),              # BMA: kein Brandverlauf
    ]
    f = metrics.fire_course(metrics.evaluate(incidents, CFG))
    assert f["total"] == 2
    assert (f["to_control"]["valid"], f["to_control"]["median"], f["to_out"]["median"]) == (1, 20.0, 50.0)
    assert [(t["tactic"], t["count"]) for t in f["tactics"]] == [("Innenangriff", 1)]
    assert (f["fire_watches"], f["fire_watch_hours"]) == (1, 2.0)


def test_casualties_distinguish_zero_from_not_reported():
    incidents = [make_incident(id=1, rescued=2, injured=1, deceased=0), make_incident(id=2), make_incident(id=3, rescued=0)]
    c = metrics.casualties(metrics.evaluate(incidents, CFG))
    assert c["fields"]["rescued"] == {"total": 2, "incidents": 1, "reported": 2}
    assert c["fields"]["deceased"] == {"total": 0, "incidents": 0, "reported": 1}
    assert c["fields"]["injured_firefighters"]["reported"] == 0
    assert c["incidents_with_persons"] == 1


def test_attendance_overview_counts_functions_and_agt():
    people = [{"id": 1, "name": "Muster, Max", "role": "Einheitsführer", "agt": 0, "agt_min": 0},
              {"id": 2, "name": "Beispiel, Erika", "role": "Maschinist", "agt": 1, "agt_min": 12}]
    incidents = [make_incident(id=1, people=people), make_incident(id=2, people=[people[1]])]
    a = metrics.attendance_overview(metrics.evaluate(incidents, CFG))
    erika = next(m for m in a["members"] if m["id"] == 2)
    assert erika["functions"] == {"Maschinist": 2} and (erika["agt_incidents"], erika["agt_minutes"]) == (2, 24)
    assert a["functions"] == [{"role": "Maschinist", "count": 2, "people": 1}, {"role": "Einheitsführer", "count": 1, "people": 1}]


def test_abort_reasons_ignore_standard_suffix_in_brackets():
    texts = ["Täuschungsalarm einer automatischen BMA (DIN VDE 0833-1)", "Täuschungsalarm einer automatischen BMA (DIN VDE 0833-",
             "täuschungsalarm einer automatischen BMA"]
    incidents = [make_incident(id=n, abort_reason=t) for n, t in enumerate(texts, 1)]
    reasons = metrics.aborts(metrics.evaluate(incidents, CFG))["reasons"]
    assert reasons == [{"reason": "Täuschungsalarm einer automatischen BMA", "count": 3, "kind": "false_alarm"}]


def test_unreadable_vehicle_times_do_not_break_the_evaluation():
    """Eine fehlerhafte Fahrzeugzeit ergibt „nicht angegeben“, statt die ganze Auswertung abstürzen zu lassen."""
    incident = make_incident(vehicles={
        "02/45": vehicle("02/45", 6, "kaputt", "2025-03-12T10:07:00"),     # Text bzw. ISO-Zeitstempel statt Uhrzeit
    })
    m = metrics.incident_metrics(incident, CFG)
    assert m["vehicles"]["02/45"]["turnout_min"] is None
    assert m["vehicles"]["02/45"]["arrival_min"] == 7
