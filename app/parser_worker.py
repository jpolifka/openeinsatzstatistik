"""Dateileser in kurzlebigen Prozessen: begrenzte Parallelität, Laufzeit und Rückgabemenge."""
import datetime as dt
import decimal
import json
import multiprocessing
import sys
import threading

GENERIC_ERROR = "Die Datei konnte nicht gelesen werden. Ist es ein Einsatzbericht aus dem BKS-Portal?"
MAX_SECONDS = 45
MAX_RESULT_BYTES = 32 * 1024 * 1024
WORKERS = 2                                      # Dateien, die gleichzeitig gelesen werden
_slots = threading.BoundedSemaphore(WORKERS)


def read_local(kind, path):
    from app import pdf_report, xlsx_report
    if kind.endswith("_report"):
        source, filename = path
        if kind == "xlsx_report":
            return xlsx_report.parse_report(xlsx_report.read_workbook(source), filename, "")
        return pdf_report.parse_report(*pdf_report.extract_text(source), filename, "")
    return xlsx_report.read_workbook(path) if kind == "xlsx" else pdf_report.extract_text(path)


# Ergebnis des Kindprozesses als JSON statt Pickle: der Kindprozess liest fremde Dateien, der Hauptprozess
# darf dessen Antwort nie ausführen. Nicht-JSON-Typen tragen eine Kennung; unbekannte Typen sind ein Fehler.
_TAGGED = {"tuple": tuple, "datetime": dt.datetime.fromisoformat, "date": dt.date.fromisoformat,
           "time": dt.time.fromisoformat, "decimal": decimal.Decimal}


def encode(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, list):
        return [encode(v) for v in value]
    if isinstance(value, tuple):
        return {"$": "tuple", "v": [encode(v) for v in value]}
    if isinstance(value, dict):
        return {"$": "dict", "v": [[encode(k), encode(v)] for k, v in value.items()]}
    # datetime ist ein date: genauer Typ zuerst
    for tag, kind in (("datetime", dt.datetime), ("date", dt.date), ("time", dt.time)):
        if isinstance(value, kind):
            return {"$": tag, "v": value.isoformat()}
    if isinstance(value, decimal.Decimal):
        return {"$": "decimal", "v": str(value)}
    raise TypeError(f"Nicht übertragbarer Typ im Leseergebnis: {type(value).__name__}")


def decode(value):
    if isinstance(value, list):
        return [decode(v) for v in value]
    if not isinstance(value, dict):
        return value
    tag, content = value.get("$"), value.get("v")
    if tag == "dict":
        return {decode(k): decode(v) for k, v in content}
    if tag == "tuple":
        return tuple(decode(v) for v in content)
    if tag in _TAGGED:
        return _TAGGED[tag](content)
    raise ValueError("Unbekanntes Leseergebnis.")


def _child(connection, kind, path):
    try:
        if sys.platform.startswith("linux"):
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (MAX_SECONDS, MAX_SECONDS))
        result = read_local(kind, path)
        connection.send_bytes(json.dumps({"ok": True, "result": encode(result)}).encode())
    except Exception as error:
        # Nur eigene Fachmeldungen (ValueError) gehen an den Benutzer; alles andere ist intern
        message = str(error) if isinstance(error, ValueError) and str(error) else GENERIC_ERROR
        connection.send_bytes(json.dumps({"ok": False, "result": message}).encode())
    finally:
        connection.close()


def read(kind, path):
    # Mehrere Dateien eines Uploads (und mehrere Benutzer) warten auf einen der Plätze
    if not _slots.acquire(timeout=MAX_SECONDS * 2):
        raise ValueError("Zu viele Dateien werden gleichzeitig gelesen. Bitte später erneut versuchen.")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(child, kind, path), daemon=True)
    try:
        process.start()
        child.close()
        if not parent.poll(MAX_SECONDS):
            raise ValueError("Die Datei konnte nicht innerhalb von 45 Sekunden gelesen werden.")
        answer = json.loads(parent.recv_bytes(MAX_RESULT_BYTES))
        if not answer["ok"]:
            raise ValueError(answer["result"])
        return decode(answer["result"])
    except (EOFError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError("Die Datei überschreitet die Verarbeitungsgrenzen oder ist beschädigt.") from error
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join()
        parent.close()
        child.close()
        _slots.release()
