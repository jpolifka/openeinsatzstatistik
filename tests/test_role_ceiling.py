# -*- coding: utf-8 -*-
"""Eine Rolle darf nie mehr Rechte enthalten, als ihr Autor selbst hat (Rechte-Eskalation über die Rollenpflege)."""
from test_access import _as, world  # noqa: F401  (world ist eine Fixture)


def _role_id(client, key):
    return next(r["id"] for r in client.get("/api/admin/roles").json()["roles"] if r["key"] == key)


def _delegate(client):
    """Superadmin richtet einen Delegierten ein, der nur Rollen pflegen und vergeben darf."""
    _as(client, "admin@example.org")
    body = {"label": "Rollenpfleger", "scope": "vg", "vg": "vg-a", "permissions": ["roles.manage", "users.grant"]}
    assert client.post("/api/admin/roles", json=body).status_code == 200
    role_id = _role_id(client, "rollenpfleger")
    assert client.put(f"/api/admin/roles/{role_id}", json={**body, "grants": [role_id]}).status_code == 200
    assert client.post("/api/admin/memberships", json={"email": "pfleger@example.org", "role": "rollenpfleger",
                                                       "scope": "vg", "slug": "vg-a"}).status_code == 200
    return role_id


def test_role_manager_cannot_create_role_with_more_rights(world):
    client, _ = world
    role_id = _delegate(client)
    _as(client, "pfleger@example.org", "vg:vg-a")
    everything = [p["key"] for p in client.get("/api/admin/roles").json()["permissions"] if "vg" in p["scopes"]]
    created = client.post("/api/admin/roles", json={"label": "Alles", "scope": "vg", "vg": "vg-a",
                                                    "permissions": everything, "granted_by": [role_id]})
    assert created.status_code == 403
    assert "Alles" not in {r["label"] for r in client.get("/api/admin/roles").json()["roles"]}


def test_role_manager_may_create_role_within_own_rights(world):
    client, _ = world
    role_id = _delegate(client)
    _as(client, "pfleger@example.org", "vg:vg-a")
    created = client.post("/api/admin/roles", json={"label": "Verteiler", "scope": "vg", "vg": "vg-a",
                                                    "permissions": ["users.grant"], "granted_by": [role_id]})
    assert created.status_code == 200


def test_role_without_delegator_in_reach_is_free_to_define(world):
    """Aufgabenteilung: Der Wehrleiter definiert die Rolle „Gruppenführer“ (mit Namen), die der Wehrführer vergibt."""
    client, _ = world
    _as(client, "vglead@example.org")
    lead = _role_id(client, "lead")
    editor = _role_id(client, "editor")
    created = client.post("/api/admin/roles", json={"label": "Gruppenführer", "scope": "tenant", "vg": "vg-a",
                                                    "parent": editor, "permissions": ["tenant.keywords"],
                                                    "granted_by": [lead]})
    assert created.status_code == 200


def test_second_hop_through_a_grantable_role_is_refused(world):
    """Rolle „Hebel“ (vergebbar für den Pfleger) darf keine stärkere Rolle weitergeben."""
    client, _ = world
    role_id = _delegate(client)
    _as(client, "pfleger@example.org", "vg:vg-a")
    everything = [p["key"] for p in client.get("/api/admin/roles").json()["permissions"] if "vg" in p["scopes"]]
    # Ohne Verteiler durch ihn selbst ist „Alles“ nur eine Definition ...
    assert client.post("/api/admin/roles", json={"label": "Alles", "scope": "vg", "vg": "vg-a",
                                                 "permissions": everything}).status_code == 200
    everything_id = _role_id(client, "alles")
    # ... aber nicht mehr, wenn eine Rolle, die er erreichen kann, sie vergeben darf
    hebel = client.post("/api/admin/roles", json={"label": "Hebel", "scope": "vg", "vg": "vg-a",
                                                  "permissions": ["users.grant"], "granted_by": [role_id],
                                                  "grants": [everything_id]})
    assert hebel.status_code == 403
    again = client.put(f"/api/admin/roles/{everything_id}", json={"label": "Alles", "scope": "vg", "vg": "vg-a",
                                                                 "permissions": everything, "granted_by": [role_id]})
    assert again.status_code == 403
