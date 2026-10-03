"""Upload-Limit bereits vor bzw. während der Multipart-Verarbeitung erzwingen."""
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class RequestSizeLimit:
    def __init__(self, app, max_bytes=210 * 1024 * 1024):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        lengths = [value for key, value in scope.get("headers", []) if key.lower() == b"content-length"]
        try:
            if lengths and (len(lengths) != 1 or int(lengths[0]) < 0):
                raise ValueError
            oversized = bool(lengths and int(lengths[0]) > self.max_bytes)
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
                if consumed > self.max_bytes:
                    raise HTTPException(413, "Upload zu groß. Bitte kleinere Mengen einlesen.")
            return message
        await self.app(scope, limited_receive, send)
