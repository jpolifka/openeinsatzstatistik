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
