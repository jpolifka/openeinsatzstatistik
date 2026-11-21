# -*- coding: utf-8 -*-
"""Verwaltung: Personenstamm einer Wehr (anlegen, umbenennen, ausgeschieden, zusammenführen, Wehr wechseln).

Der Stamm ist zugleich der Abgleich der eingelesenen Namen: Die Liste zeigt je Person, wo sie vorkommt, und
weist auf ähnliche Einträge hin (Schreibvarianten, gleiche Initialen). Recht: SETTINGS der jeweiligen Wehr (Wehrführung, nicht der Erfasser von Einsätzen oder Übungen).
"""
import difflib

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app import names, store, tenancy
from app.admin.common import access, log
from app.rbac import SETTINGS

router = APIRouter()


class PersonIn(BaseModel):
    last_name: str = Field(min_length=1, max_length=60)
    first_name: str = Field(default="", max_length=60)
    active: bool = True


class MergeIn(BaseModel):
    into: int


class TransferIn(BaseModel):
    to_slug: str = Field(max_length=80)


def _display(last, first):
    return f"{last}, {first}".strip(", ")


def _clean(body):
    last, first = body.last_name.strip(), body.first_name.strip()
    if not last:
        raise HTTPException(422, "Bitte einen Nachnamen angeben.")
    return last, first


def _similar(people):
    """Je Person die Einträge, die auf dieselbe Person hindeuten könnten: gleicher Nachname, Namensanfang oder Tippfehler im
    Nachnamen bei gleicher Initiale des Vornamens."""
    keyed = [(p["id"], names.normalize(p["last_name"]), names.normalize(p["first_name"])) for p in people]
    result = {p["id"]: [] for p in people}
    for i, (id_a, last_a, first_a) in enumerate(keyed):
        for id_b, last_b, first_b in keyed[i + 1:]:
            same_first = not first_a or not first_b or first_a[:1] == first_b[:1]
            close = last_a == last_b or (min(len(last_a), len(last_b)) >= 3 and (
                last_a.startswith(last_b) or last_b.startswith(last_a)        # Rott ↔ Röttgen
                or difflib.SequenceMatcher(None, last_a, last_b).ratio() >= 0.8))
            if close and same_first:
                result[id_a].append(id_b)
                result[id_b].append(id_a)
    return result


def _rows(con):
    """Personen mit Zahl der Einsätze und Übungen sowie Hinweisen auf ähnliche Einträge."""
    incidents = {r[0]: (r[1], r[2]) for r in con.execute(
        "SELECT a.member_id, COUNT(*), MAX(i.started_at) FROM attendance a JOIN incident i ON i.id = a.incident_id "
        "GROUP BY a.member_id")}
    trainings = {r[0]: r[1] for r in con.execute(
        "SELECT member_id, COUNT(*) FROM training_attendance GROUP BY member_id")}
    people = sorted((dict(r) for r in con.execute("SELECT id, name, last_name, first_name, active FROM member")),
                    key=lambda p: names.sort_key(p["name"]))
    similar = _similar(people)
    by_id = {p["id"]: p for p in people}
    for p in people:
        count, last = incidents.get(p["id"], (0, None))
        p.update(active=bool(p["active"]), incidents=count, last=last, trainings=trainings.get(p["id"], 0),
                 similar=[{"id": i, "name": by_id[i]["name"]} for i in similar[p["id"]]])
    return people


def _person(con, member_id):
    row = con.execute("SELECT id, name, last_name, first_name, active FROM member WHERE id = ?",
                      (member_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Person nicht gefunden.")
    return row


def _free_name(con, name, own_id=None):
    row = con.execute("SELECT id FROM member WHERE name = ?", (name,)).fetchone()
    if row and row["id"] != own_id:
        raise HTTPException(409, f"„{name}“ gibt es schon im Personenstamm.")


def _listing(con):
    return {"members": _rows(con)}


@router.get("/api/admin/{slug}/members")
def get_members(slug: str, a: tenancy.Access = Depends(access)):
    with a.tenant(slug, SETTINGS).connection() as con:
        return _listing(con)


@router.post("/api/admin/{slug}/members")
def create_member(slug: str, body: PersonIn, a: tenancy.Access = Depends(access)):
    last, first = _clean(body)
    with a.tenant(slug, SETTINGS).connection() as con:
        _free_name(con, _display(last, first))
        known = store.MemberDirectory(con).find(last, first)
        if known is not None:
            # Der Namensabgleich würde die Person beim Einlesen ohnehin dieser zuordnen: nicht doppelt anlegen
            raise HTTPException(409, f"Passt zu „{_person(con, known)['name']}“, das es schon gibt. "
                                     "Bei einer anderen Person bitte den Namen unterscheidbar schreiben.")
        member_id = con.execute(
            "INSERT INTO member (name, last_name, first_name, sort_order, active) "
            "VALUES (?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM member), ?)",
            (_display(last, first), last, first, int(body.active))).lastrowid
        log.info("Person %s in %s angelegt", member_id, slug)
        return _listing(con)


@router.put("/api/admin/{slug}/members/{member_id}")
def update_member(slug: str, member_id: int, body: PersonIn, a: tenancy.Access = Depends(access)):
    last, first = _clean(body)
    with a.tenant(slug, SETTINGS).connection() as con:
        _person(con, member_id)
        _free_name(con, _display(last, first), member_id)
        con.execute("UPDATE member SET name = ?, last_name = ?, first_name = ?, active = ? WHERE id = ?",
                    (_display(last, first), last, first, int(body.active), member_id))
        return _listing(con)


@router.post("/api/admin/{slug}/members/{member_id}/merge")
def merge_member(slug: str, member_id: int, body: MergeIn, a: tenancy.Access = Depends(access)):
    """Doppelten Eintrag in eine andere Person überführen: Einsatzteilnahmen und Übungen wandern, der Eintrag entfällt.
    Ist die Person in einem Einsatz mit beiden Einträgen geführt, bleibt die Zeile der Zielperson."""
    if body.into == member_id:
        raise HTTPException(422, "Die Person lässt sich nicht mit sich selbst zusammenführen.")
    with a.tenant(slug, SETTINGS).connection() as con:
        source, target = _person(con, member_id), _person(con, body.into)
        for table, key in (("attendance", "incident_id"), ("training_attendance", "training_id")):
            con.execute(f"DELETE FROM {table} WHERE member_id = ? AND {key} IN "
                        f"(SELECT {key} FROM {table} WHERE member_id = ?)", (member_id, body.into))
            con.execute(f"UPDATE {table} SET member_id = ? WHERE member_id = ?", (body.into, member_id))
        con.execute("DELETE FROM member WHERE id = ?", (member_id,))
        log.info("Person %s mit %s in %s zusammengeführt", source["id"], target["id"], slug)
        return _listing(con)


@router.delete("/api/admin/{slug}/members/{member_id}")
def delete_member(slug: str, member_id: int, a: tenancy.Access = Depends(access)):
    """Nur Personen ohne Einsätze und Übungen (sonst ausscheiden lassen oder zusammenführen)."""
    with a.tenant(slug, SETTINGS).connection() as con:
        _person(con, member_id)
        if (con.execute("SELECT COUNT(*) FROM attendance WHERE member_id = ?", (member_id,)).fetchone()[0]
                or con.execute("SELECT COUNT(*) FROM training_attendance WHERE member_id = ?",
                               (member_id,)).fetchone()[0]):
            raise HTTPException(409, "Die Person hat Einsätze oder Übungen. Bitte als ausgeschieden kennzeichnen "
                                     "oder mit einem anderen Eintrag zusammenführen.")
        con.execute("DELETE FROM member WHERE id = ?", (member_id,))
        return _listing(con)


@router.post("/api/admin/{slug}/members/{member_id}/transfer")
def transfer_member(slug: str, member_id: int, body: TransferIn, a: tenancy.Access = Depends(access)):
    """Wechsel in eine andere Wehr derselben VG: dort wird die Person angelegt bzw. wieder aktiv, hier scheidet sie aus.
    Bisherige Einsätze und Übungen bleiben bei dieser Wehr; die Wehr, in die sie wechselt, beginnt ohne Historie."""
    source = a.tenant(slug, SETTINGS)
    target = a.tenant(body.to_slug, SETTINGS)
    if target.slug == source.slug or target.vg_id != source.vg_id:
        raise HTTPException(422, "Ein Wechsel ist nur in eine andere Wehr derselben Verbandsgemeinde möglich.")
    with source.connection() as con:
        person = _person(con, member_id)
    last, first = person["last_name"] or person["name"], person["first_name"] or ""
    with target.connection() as con:
        known = store.MemberDirectory(con).find(last, first)
        if known is not None:
            con.execute("UPDATE member SET active = 1 WHERE id = ?", (known,))
        else:
            con.execute("INSERT INTO member (name, last_name, first_name, sort_order) "
                        "VALUES (?, ?, ?, (SELECT COALESCE(MAX(sort_order), 0) + 1 FROM member))",
                        (person["name"], last, first))
    with source.connection() as con:
        con.execute("UPDATE member SET active = 0 WHERE id = ?", (member_id,))
        log.info("Person %s von %s nach %s gewechselt", member_id, source.slug, target.slug)
        return _listing(con)

