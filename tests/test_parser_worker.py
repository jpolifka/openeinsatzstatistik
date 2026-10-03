"""Echte Prozessgrenzen mit synthetischen Excel-Dateien."""
import pytest
from app import parser_worker
from test_xlsx_report import make_workbook


def test_isolated_xlsx_reader(tmp_path):
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(make_workbook())
    assert parser_worker.read("xlsx", str(path)) == parser_worker.read_local("xlsx", str(path))


def test_isolated_reader_reports_invalid_file(tmp_path):
    path = tmp_path / "invalid.pdf"
    path.write_bytes(b"kein PDF")
    with pytest.raises(ValueError):
        parser_worker.read("pdf", str(path))


def test_full_report_parsing_and_unit_projection_are_isolated(tmp_path):
    from app import report, xlsx_report
    from conftest import CFG
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(make_workbook())
    parse = report.parser(str(path), path.name)
    assert parse(CFG.unit_prefix) == xlsx_report.parse_report(xlsx_report.read_workbook(str(path)), path.name, CFG.unit_prefix)
    changed = parse(CFG.unit_prefix)
    changed["vehicles"][0]["crew"] = 99
    assert parse(CFG.unit_prefix)["vehicles"][0]["crew"] != 99


def test_timeout_terminates_worker_and_releases_slot(tmp_path, monkeypatch):
    path = tmp_path / "synthetic.xlsx"
    path.write_bytes(make_workbook())
    monkeypatch.setattr(parser_worker, "MAX_SECONDS", 0.001)
    with pytest.raises(ValueError):
        parser_worker.read("xlsx", str(path))
    monkeypatch.setattr(parser_worker, "MAX_SECONDS", 45)
    assert parser_worker.read("xlsx", str(path))
