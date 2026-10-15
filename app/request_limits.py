"""Upload-Limit bereits vor bzw. während der Multipart-Verarbeitung erzwingen.

Fast alle Anfragen sind kleines JSON; nur wenige Wege nehmen Dateien an. Jeder Weg hat deshalb sein eigenes Limit
(UPLOAD_ROUTES), alles andere höchstens DEFAULT_LIMIT – sonst könnte ein Textfeld Hunderte MB im Speicher belegen.
"""
import re

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

MB = 1024 * 1024
DEFAULT_LIMIT = 2 * MB
# Berichte: etwas mehr als importing.UPLOAD_MAX_BYTES (Multipart-Rahmen); AVV-PDF 10 MB; Stichwortkatalog 2 MB
UPLOAD_ROUTES = (
    (re.compile(r"/api/reports"), 105 * MB),
    (re.compile(r"/api/dpa/[^/]+/upload"), 11 * MB),
    (re.compile(r"/api/admin/(?:vgs/[^/]+|[^/]+)/keywords/import"), 3 * MB),
)


class RequestSizeLimit:
    def __init__(self, app, max_bytes=DEFAULT_LIMIT, routes=()):
        self.app, self.max_bytes, self.routes = app, max_bytes, tuple(routes)

    def limit_for(self, path):
        return next((limit for pattern, limit in self.routes if pattern.fullmatch(path)), self.max_bytes)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = self.limit_for(scope.get("path", ""))
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        try:
            if lengths and (len(lengths) != 1 or int(lengths[0]) < 0):
                raise ValueError
            oversized = bool(lengths and int(lengths[0]) > limit)
        except ValueError:
            return await JSONResponse({"detail": "Ungültige Upload-Größe."}, 400)(scope, receive, send)
        if oversized:
            return await JSONResponse({"detail": "Upload zu groß. Bitte kleinere Mengen einlesen."}, 413)(scope, receive, send)
        consumed = 0
        async def limited_receive():
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > limit:
                    raise HTTPException(413, "Upload zu groß. Bitte kleinere Mengen einlesen.")
            return message
        await self.app(scope, limited_receive, send)
