"""Dateileser in kurzlebigen Prozessen: begrenzte Parallelität, Laufzeit und Rückgabemenge."""
import multiprocessing
import sys
import threading

MAX_SECONDS = 45
MAX_RESULT_BYTES = 32 * 1024 * 1024
_slots = threading.BoundedSemaphore(2)


def read_local(kind, path):
    from app import pdf_report, xlsx_report
    if kind.endswith("_report"):
        source, filename = path
        if kind == "xlsx_report":
            return xlsx_report.parse_report(xlsx_report.read_workbook(source), filename, "")
        return pdf_report.parse_report(*pdf_report.extract_text(source), filename, "")
    return xlsx_report.read_workbook(path) if kind == "xlsx" else pdf_report.extract_text(path)


def _child(connection, kind, path):
    try:
        if sys.platform.startswith("linux"):
            import resource
            resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
            resource.setrlimit(resource.RLIMIT_CPU, (MAX_SECONDS, MAX_SECONDS))
        result = read_local(kind, path)
        connection.send((True, result))
    except Exception as error:
        connection.send((False, str(error) or type(error).__name__))
    finally:
        connection.close()


def read(kind, path):
    if not _slots.acquire(timeout=1):
        raise ValueError("Zu viele Dateien werden gleichzeitig gelesen. Bitte später erneut versuchen.")
    ctx = multiprocessing.get_context("spawn")
    parent, child = ctx.Pipe(duplex=False)
    process = ctx.Process(target=_child, args=(child, kind, path), daemon=True)
    try:
        process.start()
        child.close()
        if not parent.poll(MAX_SECONDS):
            raise ValueError("Die Datei konnte nicht innerhalb von 45 Sekunden gelesen werden.")
        import pickle
        success, result = pickle.loads(parent.recv_bytes(MAX_RESULT_BYTES))
        if not success:
            raise ValueError(result)
        return result
    except (EOFError, OSError) as error:
        raise ValueError("Die Datei überschreitet die Verarbeitungsgrenzen oder ist beschädigt.") from error
    finally:
        if process.is_alive():
            process.terminate()
        if process.pid is not None:
            process.join()
        parent.close()
        child.close()
        _slots.release()
