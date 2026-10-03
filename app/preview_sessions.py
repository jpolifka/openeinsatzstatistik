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
        size = len(json.dumps(reports, default=str, ensure_ascii=False).encode())
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
