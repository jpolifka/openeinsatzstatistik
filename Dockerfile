FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY static ./static

# Tests: docker build --target test -t pdf2einsatz-test . && docker run --rm pdf2einsatz-test
FROM base AS test
COPY requirements-dev.txt pytest.ini ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q"]

FROM base AS app
EXPOSE 8112
# Nur ein Worker: die PDF-Vorschau liegt bis zur Übernahme im Prozessspeicher (main.PreviewSessions)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8112"]
