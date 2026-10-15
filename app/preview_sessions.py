"""Begrenzte, benutzergebundene Importvorschauen mit explizitem Abbruch."""
import contextlib
import json
import threading
import time
import uuid

from fastapi import HTTPException


# ---------------------------------------------------------------- PDF-Vorschau im Speicher
class PreviewSessions:
    """Gelesene Berichte bis zur Übernahme. Liegt im Prozess – daher nur ein uvicorn-Worker.

    Eine Vorschau gehört dem Benutzer, der sie angelegt hat, und der Wehr, für die gelesen wurde."""
    TTL = 60 * 60
    MAX_SESSIONS = 128
    MAX_PER_OWNER = 8
    MAX_BYTES = 64 * 1024 * 1024

    def __init__(self):
        self._sessions = {}
        self._lock = threading.Lock()

    def add(self, reports, owner):
        """reports: [(bericht, slug der Wehr, für die er gelesen wurde)]."""
        token = uuid.uuid4().hex
        if not reports:
            return token
        size = sum(len(json.dumps({k: v for k, v in r.items() if k != "_data"}, default=str, ensure_ascii=False).encode())
                   + len(r.get("_data") or b"") for r, _ in reports)
        with self._lock:
            self._expire()
            if len(self._sessions) >= self.MAX_SESSIONS or sum(s["owner"] == owner for s in self._sessions.values()) >= self.MAX_PER_OWNER:
                raise HTTPException(429, "Zu viele offene Vorschauen. Bitte vorhandene Berichte übernehmen oder später erneut versuchen.")
            if size + sum(s.get("size", 0) for s in self._sessions.values()) > self.MAX_BYTES:
                raise HTTPException(413, "Die Vorschauen sind zu groß. Bitte kleinere Mengen einlesen.")
            self._sessions[token] = {"time": time.time(), "owner": owner,
                                     "size": size,
                                     "reports": {r["filename"]: (r, slug) for r, slug in reports}}
        return token

    def get(self, token, filename, owner):
        """(bericht, slug) oder (None, None), auch wenn die Vorschau einem anderen Benutzer gehört."""
        with self._lock:
            self._expire()
            session = self._sessions.get(token)
            if not session or session["owner"] != owner:
                return None, None
            return session["reports"].get(filename, (None, None))

    def cancel(self, token, owner):
        """Nur eigene Vorschauen verwerfen; fehlgeschlagene Übernahmen nicht wiederherstellen."""
        with self._lock:
            session = self._sessions.get(token)
            if session and session["owner"] == owner:
                session["cancelled"] = True
                del self._sessions[token]

    @contextlib.contextmanager
    def claim(self, token, filename, owner):
        """Bericht zur Übernahme entnehmen: ein zweiter Aufruf (Doppelklick) findet ihn nicht mehr.
        Scheitert die Übernahme, liegt er wieder bereit."""
        entry = None
        with self._lock:
            session = self._sessions.get(token)
            if session and session["owner"] == owner and session["time"] >= time.time() - self.TTL:
                entry = session["reports"].pop(filename, None)
                if entry:
                    session["inflight"] = session.get("inflight", 0) + 1
        try:
            yield entry or (None, None)
        except BaseException:
            if entry:
                with self._lock:
                    if not session.get("cancelled"):
                        session["reports"][filename] = entry
            raise
        finally:
            if entry:
                with self._lock:
                    session["inflight"] -= 1
                    if not session["reports"] and not session["inflight"] and self._sessions.get(token) is session:
                        del self._sessions[token]

    def _expire(self):
        cutoff = time.time() - self.TTL
        for token in [t for t, s in self._sessions.items() if s["time"] < cutoff]:
            self._sessions[token]["cancelled"] = True
            del self._sessions[token]


# ---------------------------------------------------------------- Lesen im Hintergrund
class ReadJobs:
    """Berichte, die im Hintergrund gelesen werden: Der Upload antwortet sofort, die Oberfläche fragt den
    Fortschritt ab. So bleibt jede Anfrage kurz (Proxys wie Cloudflare brechen nach etwa 100 s ab).
    Liegt im Prozess wie PreviewSessions; ein Job gehört dem Benutzer, der ihn gestartet hat."""
    TTL = 60 * 60
    MAX_RUNNING_PER_OWNER = 2

    def __init__(self):
        self._jobs = {}
        self._lock = threading.Lock()

    def start(self, owner, total, work):
        """work(progress) läuft in einem eigenen Thread und liefert das Ergebnis; progress() zählt gelesene Dateien."""
        job_id = uuid.uuid4().hex
        job = {"owner": owner, "time": time.time(), "total": total, "read": 0, "result": None, "error": None}
        with self._lock:
            cutoff = time.time() - self.TTL
            for key in [k for k, j in self._jobs.items() if j["time"] < cutoff]:
                del self._jobs[key]
            running = sum(j["owner"] == owner and j["result"] is None and j["error"] is None
                          for j in self._jobs.values())
            if running >= self.MAX_RUNNING_PER_OWNER:
                raise HTTPException(429, "Es werden schon Berichte eingelesen. Bitte erst das Ergebnis abwarten.")
            self._jobs[job_id] = job

        def progress():
            with self._lock:
                job["read"] += 1

        def run():
            try:
                result = work(progress)
                with self._lock:
                    job["result"] = result
            except HTTPException as e:
                with self._lock:
                    job["error"] = (e.status_code, e.detail)
            except Exception as e:  # unerwartet: melden statt still hängen
                with self._lock:
                    job["error"] = (500, str(e) or type(e).__name__)

        threading.Thread(target=run, daemon=True, name=f"read-{job_id[:8]}").start()
        return job_id

    def status(self, job_id, owner):
        """{read, total, done, result|error} oder None (unbekannt oder fremder Job). Ein fertiger Job wird
        mit der Abfrage entfernt."""
        with self._lock:
            job = self._jobs.get(job_id)
            if not job or job["owner"] != owner:
                return None
            done = job["result"] is not None or job["error"] is not None
            if done:
                del self._jobs[job_id]
            return {"read": job["read"], "total": job["total"], "done": done,
                    "result": job["result"], "error": job["error"]}
