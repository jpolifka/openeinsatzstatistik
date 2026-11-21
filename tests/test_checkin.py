# -*- coding: utf-8 -*-
"""QR-Anmeldung zum Übungsdienst ohne Benutzerkonto: Token, Sperren, Anlegen der Übung des Tages, Rechte."""
import datetime as dt

import pytest

from app import auth, checkin, db, tenancy, trainings
from conftest import grant, login, make_tenant

TODAY = dt.datetime(2026, 11, 21, 18, 30)


@pytest.fixture
def setup(make_client, monkeypatch):
    """Anmeldung an (kein Cookie bei den öffentlichen Aufrufen), feste Uhrzeit."""
    _vg, tenant_id = make_tenant("wehr-a1")
    grant("editor@example.org", "editor", tenant_id)
    grant("viewer@example.org", "viewer", tenant_id)
    client = make_client(login=True)
    monkeypatch.setattr(checkin.dt, "datetime", type("D", (dt.datetime,), {"now": classmethod(lambda c: TODAY)}))
    monkeypatch.setattr(checkin, "LIMITS", {"client": (1000, 60), "tenant": (1000, 60)})
    return client


def _tenant():
    return tenancy.vg_tenants(1)[0]


def _link():
    return f"{checkin.PATH}{checkin.token_for(_tenant())}"


def _trainings():
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        return trainings.load(con)


def _post(client, first="Erika", last="Beispiel", link=None):
    return client.post(link or _link(), data={"first_name": first, "last_name": last})


def test_public_without_login_and_form(setup):
    r = setup.get(_link())
    assert r.status_code == 200 and "Übungsdienst" in r.text and "Wehr wehr-a1" in r.text


def test_invalid_token_is_404(setup):
    slug = _link().rsplit("/", 1)[1].split(".")[0]
    for token in ("", "x", f"{slug}.abc", f"{slug}.{'0' * 64}", "unbekannt.abc"):
        assert setup.get(f"/checkin/{token}").status_code == 404
    assert _trainings() == []


def test_first_checkin_creates_training_and_member(setup):
    r = _post(setup)
    assert r.status_code == 200 and "Erika Beispiel" in r.text
    (t,) = _trainings()
    assert t["topic"] == "Übung 21.11.2026" and t["started_at"].startswith("2026-11-21")
    assert [p["name"] for p in t["participants"]] == ["Beispiel, Erika"]


def test_second_checkin_reuses_training_and_is_idempotent(setup):
    _post(setup)
    _post(setup)
    _post(setup, "Max", "Muster")
    (t,) = _trainings()
    assert sorted(p["name"] for p in t["participants"]) == ["Beispiel, Erika", "Muster, Max"]


def test_existing_training_of_the_day_is_used(setup):
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        existing = trainings.create(con, {"topic": "Atemschutz", "started_at": "2026-11-21T19:30",
                                          "ended_at": "2026-11-21T21:00"})
    _post(setup)
    (t,) = _trainings()
    assert t["id"] == existing and t["topic"] == "Atemschutz" and t["revision"] == 1 and len(t["participants"]) == 1


def test_known_member_is_not_duplicated(setup):
    _post(setup)
    _post(setup, "E.", "Beispiel")      # gleicher Name, andere Schreibweise des Vornamens
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert con.execute("SELECT COUNT(*) FROM member").fetchone()[0] == 1


def test_missing_last_name_is_rejected(setup):
    r = _post(setup, "Erika", "  ")
    assert r.status_code == 422 and "Nachnamen" in r.text and _trainings() == []


def test_name_is_escaped(setup):
    assert "<script>" not in _post(setup, "<script>", "X").text


def test_rotate_invalidates_old_link(setup):
    old = _link()
    login(setup, "editor@example.org")
    assert setup.post("/api/trainings/checkin/rotate").status_code == 200
    assert _post(setup, link=old).status_code == 404
    assert _post(setup).status_code == 200


def test_blocked_vg_without_dpa(setup):
    link = _link()
    with tenancy.central() as con:
        con.execute("UPDATE dpa SET status = 'pending'")
    assert setup.get(link).status_code == 404
    assert _post(setup, link=link).status_code == 404
    assert _trainings() == []


def test_archived_tenant_is_404(setup):
    link = _link()
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET active = 0")
    assert setup.get(link).status_code == 404


def test_rate_limit(setup, monkeypatch):
    monkeypatch.setattr(checkin, "LIMITS", {"client": (2, 60), "tenant": (1000, 60)})
    checkin._hits.clear()
    assert [_post(setup).status_code for _ in range(3)] == [200, 200, 429]


def test_admin_api_needs_edit_right(setup, monkeypatch):
    monkeypatch.setattr(auth, "BASE_URL", "https://stat.example.org")
    assert setup.get("/api/trainings/checkin").status_code == 401        # ohne Anmeldung
    login(setup, "viewer@example.org")
    for method, path in (("get", "/api/trainings/checkin"), ("get", "/api/trainings/checkin.svg"),
                         ("post", "/api/trainings/checkin/rotate")):
        assert getattr(setup, method)(path).status_code == 403
    login(setup, "editor@example.org")
    url = setup.get("/api/trainings/checkin").json()["url"]
    assert url == f"https://stat.example.org{_link()}"
    svg = setup.get("/api/trainings/checkin.svg")
    assert svg.status_code == 200 and svg.headers["content-type"].startswith("image/svg+xml") and "<svg" in svg.text


def test_link_uses_vg_subdomain_not_request_host(setup, monkeypatch):
    monkeypatch.setattr(auth, "BASE_URL", "https://stat.example.org")
    monkeypatch.setattr(auth, "BASE_DOMAIN", "example.org")
    with tenancy.central() as con:
        con.execute("UPDATE vg SET subdomain = 'rhein'")
    login(setup, "editor@example.org")
    url = setup.get("/api/trainings/checkin", headers={"host": "evil.test"}).json()["url"]
    assert url.startswith("https://rhein.example.org/checkin/")
