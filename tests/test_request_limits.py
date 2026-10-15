"""Grenzen vor Multipart-Verarbeitung, auch ohne Content-Length."""
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from app.request_limits import RequestSizeLimit


def test_request_limits():
    app = FastAPI()
    app.add_middleware(RequestSizeLimit, max_bytes=4)
    @app.post("/")
    async def body(request: Request):
        return {"size": len(await request.body())}
    client = TestClient(app)
    assert client.post("/", content=b"1234").json() == {"size": 4}
    assert client.post("/", content=b"12345").status_code == 413
    assert client.post("/", content=iter([b"123", b"45"])).status_code == 413
    assert client.post("/", content=b"", headers={"content-length": "-1"}).status_code == 400


def test_routes_have_their_own_limit():
    import re
    app = FastAPI()
    app.add_middleware(RequestSizeLimit, max_bytes=4, routes=[(re.compile(r"/upload"), 10)])
    @app.post("/upload")
    async def upload(request: Request):
        return {"size": len(await request.body())}
    @app.post("/other")
    async def other(request: Request):
        return {"size": len(await request.body())}
    client = TestClient(app)
    assert client.post("/upload", content=b"0123456789").json() == {"size": 10}
    assert client.post("/upload", content=b"0123456789A").status_code == 413
    assert client.post("/other", content=b"12345").status_code == 413


def test_default_limit_is_small_for_json_and_upload_routes_are_listed():
    from app import request_limits
    limiter = RequestSizeLimit(None, routes=request_limits.UPLOAD_ROUTES)
    assert limiter.limit_for("/api/incidents/x:1") == request_limits.DEFAULT_LIMIT <= 2 * 1024 * 1024
    assert limiter.limit_for("/api/reports") > 100 * 1024 * 1024
    assert limiter.limit_for("/api/admin/vgs/vg-a/keywords/import") > request_limits.DEFAULT_LIMIT
    assert limiter.limit_for("/api/dpa/vg-a/upload") > request_limits.DEFAULT_LIMIT
