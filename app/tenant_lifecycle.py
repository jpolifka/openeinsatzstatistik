"""Wiederaufnehmbare Archivierung und Sicherung abgebrochener Wehr-Anlagen."""
import logging
import shutil
import uuid
from pathlib import Path

from app import db, rbac

log = logging.getLogger("pdf2einsatz")
CREATE_MARKER = ".creation-pending"


def begin_archive(con, slug, email):
    row = con.execute("SELECT id, vg_id, name FROM tenant WHERE slug = ?", (slug,)).fetchone()
    if not row:
        raise KeyError(slug)
    con.execute("INSERT OR IGNORE INTO tenant_archive (slug, target, email) VALUES (?, ?, ?)",
                (slug, f"{slug}-{uuid.uuid4().hex}", email))
    con.execute("UPDATE tenant SET active = 0 WHERE slug = ?", (slug,))


def finish_archive(slug):
    from app import tenancy
    try:
        with tenancy.central() as con:
            job = con.execute("SELECT * FROM tenant_archive WHERE slug = ?", (slug,)).fetchone()
            if not job:
                return True
            source = Path(tenancy.tenant_path(slug)).parent
            target = Path(db.DATA_DIR) / "deleted" / job["target"]
            if source.exists() and target.exists():
                raise RuntimeError("Quell- und Archivordner existieren gleichzeitig; manuelle Prüfung erforderlich")
            if source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(target))
            if not (target / "einsaetze.db").exists():
                raise RuntimeError("Archivdatenbank fehlt; zentrale Zuordnungen bleiben erhalten")
            row = con.execute("SELECT * FROM tenant WHERE slug = ?", (slug,)).fetchone()
            if row:
                rbac.log(con, job["email"], "Wehr entfernt", row["name"], row["vg_id"], row["id"])
                con.execute("DELETE FROM membership WHERE scope = 'tenant' AND scope_id = ?", (row["id"],))
                con.execute("DELETE FROM tenant WHERE id = ?", (row["id"],))
                con.execute("DELETE FROM account WHERE NOT EXISTS (SELECT 1 FROM membership m WHERE m.email = account.email)")
            con.execute("DELETE FROM tenant_archive WHERE slug = ?", (slug,))
        tenancy.forget_config(slug)
        return True
    except Exception:
        log.exception("Archivierung von %s bleibt offen; Daten und Zuordnungen werden nicht gelöscht", slug)
        return False


def recover():
    from app import tenancy
    with tenancy.central() as con:
        jobs = [row[0] for row in con.execute("SELECT slug FROM tenant_archive")]
        existing = {row[0] for row in con.execute("SELECT slug FROM tenant")}
    for slug in jobs:
        finish_archive(slug)
    root = Path(db.DATA_DIR) / "tenants"
    for marker in root.glob(f"*/{CREATE_MARKER}"):
        if marker.parent.name in existing:
            marker.unlink()
        else:
            target = Path(db.DATA_DIR) / "deleted" / f"incomplete-{marker.parent.name}-{uuid.uuid4().hex}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(marker.parent), str(target))
            log.warning("Abgebrochene Anlage gesichert: %s", target)


def retry_archives():
    from app import tenancy
    with tenancy.central() as con:
        jobs = [row[0] for row in con.execute("SELECT slug FROM tenant_archive")]
    for slug in jobs:
        finish_archive(slug)
