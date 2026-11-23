FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

# Sicherheitsupdates des Basis-Images, die dort noch nicht eingebaut sind
RUN apt-get update && apt-get -y --no-install-recommends upgrade && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY app ./app
COPY static ./static

# Tests: docker build --target test -t openeinsatzstatistik-test . && docker run --rm openeinsatzstatistik-test
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
# Laufzeitpakete sind durch requirements.txt = Lock festgelegt (CI prüft die Übereinstimmung); pip check findet Konflikte
RUN pip install --no-cache-dir -r requirements-dev.txt && pip check
COPY tests ./tests
# Mindestabdeckung: Zeilen und Zweige von app/ (gemessen ca. 99 %; die Schwelle ist bewusst niedriger)
CMD ["python", "-m", "pytest", "-q", "--cov=app", "--cov-branch", "--cov-fail-under=95"]

FROM base AS app
RUN groupadd --gid 10001 einsatz && useradd --uid 10001 --gid 10001 --no-create-home einsatz \
    && mkdir -p /daten && chown 10001:10001 /daten
# Startet als root, wechselt aber sofort auf den Besitzer des Datenordners (docker-entrypoint.sh)
COPY --chmod=755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]
EXPOSE 8112
# Der Dienst lauscht im Container auf allen Adressen; ohne Angabe von APP_BIND gilt er damit als nicht lokal
# (AUTH_DISABLED wird abgelehnt). docker-compose überschreibt das mit der tatsächlichen Bindung.
ENV APP_BIND=0.0.0.0
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8112/health', timeout=3).close()"
# Nur ein Worker: die Vorschau liegt bis zur Übernahme im Prozessspeicher (preview_sessions.py)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8112"]
