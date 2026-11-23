# -*- coding: utf-8 -*-
"""QR-Anmeldung zum Übungsdienst ohne Benutzerkonto: Token, PIN je Übung, Quarantäne, Sperren, Rechte."""
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


def _training(started="2026-11-21T19:00", ended="2026-11-21T21:00"):
    """Eine Übung am Testtag; Rückgabe (ID, PIN)."""
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        tid = trainings.create(con, {"topic": "Atemschutz", "started_at": started, "ended_at": ended})
        return tid, con.execute("SELECT checkin_pin FROM training WHERE id = ?", (tid,)).fetchone()[0]


def _post(client, first="Erika", last="Beispiel", link=None, pin=None):
    return client.post(link or _link(), data={"first_name": first, "last_name": last, "pin": pin or "000000"})


def _queue():
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        return [(r["last_name"], r["first_name"]) for r in con.execute("SELECT * FROM training_checkin ORDER BY id")]


def _members():
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        return con.execute("SELECT COUNT(*) FROM member").fetchone()[0]


def test_public_without_login_and_form(setup):
    r = setup.get(_link())
    assert r.status_code == 200 and "Übungsdienst" in r.text and "Wehr wehr-a1" in r.text and 'name="pin"' in r.text


def test_invalid_token_is_404(setup):
    slug = _link().rsplit("/", 1)[1].split(".")[0]
    for token in ("", "x", f"{slug}.abc", f"{slug}.{'0' * 64}", "unbekannt.abc"):
        assert setup.get(f"/checkin/{token}").status_code == 404
    assert _trainings() == []


def test_checkin_needs_training_and_never_creates_one(setup):
    r = _post(setup)
    assert r.status_code == 403 and _trainings() == [] and _queue() == []


def test_wrong_pin_is_rejected_and_nothing_written(setup):
    _training()
    r = _post(setup, pin="123456")
    assert r.status_code == 403 and "ungültig" in r.text and _queue() == [] and _members() == 0


def test_checkin_goes_to_quarantine_not_to_master_data(setup):
    tid, pin = _training()
    r = _post(setup, pin=pin)
    assert r.status_code == 200 and "Erika Beispiel" in r.text and "bestätigt" in r.text
    assert _queue() == [("Beispiel", "Erika")] and _members() == 0
    (t,) = _trainings()
    assert t["participants"] == [] and t["revision"] == 0 and "checkin_pin" not in t


def test_pin_only_valid_on_the_day_of_the_training(setup):
    _, pin = _training("2026-11-20T19:00", "2026-11-20T21:00")      # gestern
    assert _post(setup, pin=pin).status_code == 403
    _, pin = _training("2026-11-20T19:00", "2026-11-22T21:00")      # mehrtägig, heute dabei
    assert _post(setup, pin=pin).status_code == 200


def test_lockout_after_too_many_wrong_pins_is_persistent(setup, monkeypatch):
    _, pin = _training()
    monkeypatch.setattr(trainings, "MAX_PIN_FAILS", 3)
    assert [_post(setup, pin="111111").status_code for _ in range(3)] == [403] * 3
    assert _post(setup, pin=pin).status_code == 429 and _queue() == []


def test_queue_is_capped_and_deduplicated(setup, monkeypatch):
    _, pin = _training()
    monkeypatch.setattr(trainings, "MAX_QUEUE", 2)
    _post(setup, pin=pin)
    _post(setup, "erika", "BEISPIEL", pin=pin)      # gleiche Anmeldung, andere Schreibweise
    assert len(_queue()) == 1
    _post(setup, "Max", "Muster", pin=pin)
    r = _post(setup, "Anna", "Dritte", pin=pin)
    assert r.status_code == 422 and len(_queue()) == 2


def test_missing_last_name_is_rejected(setup):
    _, pin = _training()
    r = _post(setup, "Erika", "  ", pin=pin)
    assert r.status_code == 422 and "Nachnamen" in r.text and _queue() == []


def test_name_is_escaped(setup):
    _, pin = _training()
    assert "<script>" not in _post(setup, "<script>", "X", pin=pin).text


def test_leader_accepts_and_rejects(setup):
    tid, pin = _training()
    _post(setup, "Erika", "Beispiel", pin=pin)
    _post(setup, "Max", "Muster", pin=pin)
    login(setup, "viewer@example.org")
    assert setup.post(f"/api/trainings/{tid}/checkins/accept").status_code == 403
    login(setup, "editor@example.org")
    t = setup.get("/api/trainings?year=2026").json()["trainings"][0]
    assert t["checkin_pin"] == pin and [c["name"] for c in t["checkins"]] == ["Beispiel, Erika", "Muster, Max"]
    first, second = (c["id"] for c in t["checkins"])
    assert setup.delete(f"/api/trainings/{tid}/checkins/{second}").status_code == 200
    out = setup.post(f"/api/trainings/{tid}/checkins/{first}/accept").json()
    assert [p["name"] for p in out["participants"]] == ["Beispiel, Erika"] and out["checkins"] == []
    assert out["revision"] == 1 and _members() == 1 and _queue() == []
    assert setup.delete(f"/api/trainings/{tid}/checkins/{second}").status_code == 404


def test_accept_all_and_known_member_reactivated_only_by_leader(setup):
    tid, pin = _training()
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("INSERT INTO member (name, last_name, first_name, sort_order, active) "
                    "VALUES ('Beispiel, Erika', 'Beispiel', 'Erika', 1, 0)")
    _post(setup, pin=pin)
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert con.execute("SELECT active FROM member").fetchone()[0] == 0       # öffentlicher Aufruf reaktiviert nicht
    login(setup, "editor@example.org")
    t = setup.get("/api/trainings?year=2026").json()["trainings"][0]
    assert t["checkins"][0]["match"] == "Beispiel, Erika"
    assert setup.post(f"/api/trainings/{tid}/checkins/accept").status_code == 200
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        assert con.execute("SELECT active FROM member").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM member").fetchone()[0] == 1


def test_new_pin_replaces_old_one(setup):
    tid, pin = _training()
    login(setup, "editor@example.org")
    fresh = setup.post(f"/api/trainings/{tid}/checkin-pin").json()["checkin_pin"]
    assert fresh != pin and len(fresh) == trainings.PIN_LENGTH
    assert _post(setup, pin=pin).status_code == 403 and _post(setup, pin=fresh).status_code == 200


def test_rotate_invalidates_old_link(setup):
    _, pin = _training()
    old = _link()
    login(setup, "editor@example.org")
    assert setup.post("/api/trainings/checkin/rotate").status_code == 200
    assert _post(setup, link=old, pin=pin).status_code == 404
    assert _post(setup, pin=pin).status_code == 200


def test_blocked_vg_without_dpa(setup):
    _, pin = _training()
    link = _link()
    with tenancy.central() as con:
        con.execute("UPDATE dpa SET status = 'pending'")
    assert setup.get(link).status_code == 404
    assert _post(setup, link=link, pin=pin).status_code == 404
    assert _queue() == []


def test_archived_tenant_is_404(setup):
    link = _link()
    with tenancy.central() as con:
        con.execute("UPDATE tenant SET active = 0")
    assert setup.get(link).status_code == 404


def test_rate_limit(setup, monkeypatch):
    monkeypatch.setattr(checkin, "LIMITS", {"client": (2, 60), "tenant": (1000, 60)})
    checkin._hits.clear()
    _, pin = _training()
    assert [_post(setup, pin=pin).status_code for _ in range(3)] == [200, 200, 429]


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
    assert 'xmlns="http://www.w3.org/2000/svg"' in svg.text      # sonst zeigt <img> es nicht an


def test_link_uses_vg_subdomain_not_request_host(setup, monkeypatch):
    monkeypatch.setattr(auth, "BASE_URL", "https://stat.example.org")
    monkeypatch.setattr(auth, "BASE_DOMAIN", "example.org")
    with tenancy.central() as con:
        con.execute("UPDATE vg SET subdomain = 'rhein'")
    login(setup, "editor@example.org")
    url = setup.get("/api/trainings/checkin", headers={"host": "evil.test"}).json()["url"]
    assert url.startswith("https://rhein.example.org/checkin/")
