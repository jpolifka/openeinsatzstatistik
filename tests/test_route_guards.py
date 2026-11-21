# -*- coding: utf-8 -*-
"""Wächter über alle Endpunkte: Jede Route ist eingeordnet, verlangt eine Anmeldung und liefert nie Daten einer
fremden Wehr. Ein neuer Endpunkt scheitert hier, bis er bewusst eingeordnet ist (und in test_access.py steht)."""
import pytest

from app import db, main, store, tenancy
from conftest import grant, login, make_tenant

# Ohne Anmeldung erreichbar (Middleware main.require_login)
PUBLIC = {"/health", "/login", "/logout", "/auth/verify", "/auth/code", "/"}
# Endpunkte mit Einsatz-, Wehr- oder VG-Bezug: Rechte prüft der Endpunkt je Bereich (Matrix in test_access.py)
SCOPED = {
    "/api/incidents/{key}", "/api/members", "/api/admin/{slug}/settings", "/api/admin/{slug}/keywords",
    "/api/admin/{slug}/keywords/import", "/api/admin/{slug}/keywords/template", "/api/admin/{slug}/keywords/{code}", "/api/admin/{slug}/members", "/api/admin/{slug}/members/{member_id}",
    "/api/admin/{slug}/members/{member_id}/merge", "/api/admin/{slug}/members/{member_id}/transfer",
    "/api/admin/{slug}/assets/{name}", "/api/admin/{slug}/response-plan",
    "/api/admin/vgs/{vg_slug}/fees", "/api/admin/vgs/{vg_slug}/fees/{schedule_id}", "/api/admin/vgs/{vg_slug}/fleet",
    "/api/admin/vgs/{vg_slug}/keywords", "/api/admin/vgs/{vg_slug}/keywords/import",
    "/api/admin/vgs/{vg_slug}/keywords/template", "/api/admin/vgs/{vg_slug}/keywords/{code}",
    "/api/admin/vgs/{vg_slug}/settings",
    "/api/dpa/{slug}", "/api/dpa/{slug}/document", "/api/dpa/{slug}/file", "/api/dpa/{slug}/link",
    "/api/dpa/{slug}/status", "/api/dpa/{slug}/upload",
}
# Alle übrigen API-Pfade arbeiten mit der ausgewählten Wehr bzw. dem Benutzer selbst oder verlangen Superadmin
SELECTED = {
    "/api/admin", "/api/admin/memberships", "/api/admin/parse-test", "/api/admin/role-events", "/api/admin/roles",
    "/api/admin/roles/{role_id}", "/api/admin/theme-check", "/api/admin/users/effective", "/api/branding/{slug}/{name}",
    "/api/config", "/api/dpa", "/api/evaluation", "/api/export", "/api/export/summary", "/api/feedback",
    "/api/incidents", "/api/notices", "/api/notices/{notice_id}/done", "/api/pending", "/api/pending/read",
    "/api/pending/{key}", "/api/records", "/api/records/review-all", "/api/records/{bks_record_id}/fees",
    "/api/records/{bks_record_id}/review", "/api/reports", "/api/reports/accept", "/api/reports/cancel",
    "/api/reports/jobs/{job}", "/api/scope", "/api/theme.css", "/api/trainings",
    "/api/trainings/checkin", "/api/trainings/checkin.svg", "/api/trainings/checkin/rotate",
    "/api/trainings/{training_id}", "/api/years",
}
SUPER = {
    "/api/super/overview", "/api/super/sessions", "/api/super/sessions/{session_id}", "/api/super/tenants",
    "/api/super/tenants/{slug}", "/api/super/vgs", "/api/super/vgs/{slug}",
}


def _routes():
    return {(method.upper(), path) for path, ops in main.app.openapi()["paths"].items() for method in ops}


def test_every_route_is_classified():
    paths = {path for _, path in _routes()}
    known = PUBLIC | SCOPED | SELECTED | SUPER
    assert paths - known == set(), "Neuer Endpunkt: hier und in test_access.py einordnen"
    assert known - paths == set(), "Eingeordneter Endpunkt existiert nicht mehr"


@pytest.fixture
def world(make_client):
    vg_a, a1 = make_tenant("wehr-a1", "vg-a")
    vg_b, b1 = make_tenant("wehr-b1", "vg-b")
    grant("lead@example.org", "lead", a1)
    grant("vglead@example.org", "vg_lead", vg_a)
    grant("editor@example.org", "editor", a1)
    ids = {}
    for slug in ("wehr-a1", "wehr-b1"):
        with db.connection(tenancy.tenant_path(slug)) as con:
            ids[slug] = store.create_incident(con, {"number": 1, "started_at": "2025-03-12T10:00:00", "keyword": "B2",
                                                    "place": "Altenau"}, source="pdf")
    return make_client(login=True), ids


def _fill(path, ids, own=False):
    """Platzhalter einer Route mit Werten der fremden Wehr B1 (own=True: der eigenen Wehr A1) belegen."""
    slug, vg = ("wehr-a1", "vg-a") if own else ("wehr-b1", "vg-b")
    values = {"{key}": f"{slug}:{ids[slug]}", "{slug}": slug, "{vg_slug}": vg, "{code}": "B2", "{name}": "logo",
              "{schedule_id}": "1", "{role_id}": "1", "{job}": "x", "{notice_id}": "1", "{session_id}": "x",
              "{bks_record_id}": "1", "{key}_": ""}
    for placeholder, value in values.items():
        path = path.replace(placeholder, value)
    return path


def test_api_requires_login_on_every_route(world):
    client, ids = world
    for method, path in sorted(_routes()):
        if path in PUBLIC:
            continue
        response = client.request(method, _fill(path, ids), json={} if method in ("POST", "PUT") else None)
        assert response.status_code == 401, f"{method} {path} ohne Anmeldung: {response.status_code}"


@pytest.mark.parametrize("email", ["lead@example.org", "editor@example.org", "vglead@example.org"])
def test_foreign_tenant_and_vg_are_never_served(world, email):
    """Benutzer von VG A erreichen über keine Route mit Bereichsbezug etwas aus Wehr B1 bzw. VG B."""
    client, ids = world
    client.cookies.clear()
    login(client, email)
    client.cookies.set("scope", "t:wehr-a1")
    leaked = []
    for method, path in sorted(_routes()):
        if path not in SCOPED:
            continue
        response = client.request(method, _fill(path, ids) + ("?tenant=wehr-b1" if path == "/api/members" else ""),
                                  json={} if method in ("POST", "PUT") else None)
        if response.status_code < 300:
            leaked.append((method, path, response.status_code))
    assert leaked == []


def test_foreign_incident_stays_untouched_after_write_attempts(world):
    client, ids = world
    client.cookies.clear()
    login(client, "lead@example.org")
    key = f"wehr-b1:{ids['wehr-b1']}"
    assert client.put(f"/api/incidents/{key}", json={"revision": 0, "description": "übernommen"}).status_code == 403
    assert client.delete(f"/api/incidents/{key}?revision=0").status_code == 403
    with db.connection(tenancy.tenant_path("wehr-b1")) as con:
        incident = store.load_incident(con, ids["wehr-b1"])
    assert incident["description"] != "übernommen" and incident["revision"] == 0


def test_scoped_routes_do_work_in_own_tenant(world):
    """Gegenprobe: dieselben Routen liefern in der eigenen Wehr Daten – der Wächter ist nicht leer."""
    client, ids = world
    client.cookies.clear()
    login(client, "lead@example.org")
    client.cookies.set("scope", "t:wehr-a1")
    assert client.get("/api/members?tenant=wehr-a1").status_code == 200
    assert client.get("/api/admin/wehr-a1/settings").status_code == 200
    assert client.get("/api/admin/wehr-a1/keywords").status_code == 200
