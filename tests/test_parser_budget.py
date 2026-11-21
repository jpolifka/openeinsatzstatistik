# -*- coding: utf-8 -*-
"""Die Speichergrenzen der Leseprozesse passen in das Limit des Containers."""
import os
import re

from app import parser_worker

ROOT = os.path.dirname(os.path.dirname(__file__))
MAIN_PROCESS = 300 * 1024 * 1024      # Anwendung mit einem Worker, großzügig geschätzt


def _compose(pattern):
    path = os.path.join(ROOT, "docker-compose.yml")
    if not os.path.exists(path):          # das Test-Image enthält die Compose-Datei nicht
        return None
    return re.search(pattern, open(path, encoding="utf-8").read()).group(1)


def _bytes(text):
    return int(text[:-1]) * {"m": 1024 ** 2, "g": 1024 ** 3}[text[-1]]


def test_parser_budget_fits_container_limit():
    mem, tmpfs = _compose(r"mem_limit:\s*(\w+)"), _compose(r"/tmp:size=(\w+)")
    if mem is None:
        return
    need = parser_worker.WORKERS * parser_worker.ADDRESS_SPACE + MAIN_PROCESS + _bytes(tmpfs)
    assert need < _bytes(mem)
