FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Sicherheitsupdates des Basis-Images, die dort noch nicht eingebaut sind
RUN apt-get update && apt-get -y --no-install-recommends upgrade && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY app ./app
COPY static ./static

# Tests: docker build --target test -t pdf2einsatz-test . && docker run --rm pdf2einsatz-test
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]

FROM base AS app
RUN groupadd --gid 10001 einsatz && useradd --uid 10001 --gid 10001 --no-create-home einsatz \
    && mkdir -p /daten && chown 10001:10001 /daten
# Startet als root, wechselt aber sofort auf den Besitzer des Datenordners (docker-entrypoint.sh)
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
EXPOSE 8112
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8112/health', timeout=3).close()"
# Nur ein Worker: die Vorschau liegt bis zur Übernahme im Prozessspeicher (preview_sessions.py)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8112"]
