# -*- coding: utf-8 -*-
"""Kreiskennung der Einheiten (OPTA: Kfz-Zeichen, „#“ nur bei gleichem Zeichen von Stadt und Landkreis)."""
import pytest

from app import domain, pdf_report, xlsx_report
from app.bks_common import UNIT_ID
from app.tenant_config import prefixes_of
from test_report import FULL, LEFT
from test_admin import _as, world  # noqa: F401  (Fixture)
from test_xlsx_report import make_workbook

COUNTIES = ("NR#", "MYK", "KL#", "DÜW", "AW")


@pytest.mark.parametrize("county", COUNTIES)
def test_pdf_reader_knows_unit_of_any_county(county):
    full = f"Feuerwehrhaus: FW {county}.MUS 02 Musterdorf\n" + FULL.replace("NR#.MUS", f"{county}.MUS")
    left = LEFT.replace("NR#.MUS", f"{county}.MUS")
    r = pdf_report.parse_report(full, left, "", "17-25_B2_Test.pdf", f"FL {county}.MUS ")
    assert r["unit"] == f"FW {county}.MUS 02"
    assert any(v["call_sign"] == "02/45" for v in r["vehicles"])


@pytest.mark.parametrize("county", COUNTIES)
def test_xlsx_reader_knows_unit_of_any_county(county):
    data = make_workbook()
    sheets = xlsx_report.read_workbook(data)
    sheets["Einsatzbericht"] = [tuple(c.replace("NR#", county) if isinstance(c, str) else c for c in row)
                                for row in sheets["Einsatzbericht"]]
    r = xlsx_report.parse_report(sheets, "17-25.xlsx", f"FL {county}.MUS ")
    assert r["unit"] == f"FW {county}.MUS 02"


def test_unit_id_and_county_of():
    assert all(UNIT_ID.fullmatch(f"{c}.ABC") for c in COUNTIES)
    assert not UNIT_ID.fullmatch("ABC") and not UNIT_ID.fullmatch("nr.abc")
    assert domain.county_of("NR#.ABC") == "NR" and domain.county_of("MYK.ABC") == "MYK"
    assert domain.county_of("") is None
    assert prefixes_of("FW MYK.ABC 02") == ("FL MYK.ABC ", "02/")
    assert {"NR", "MYK", "KL", "DÜW"} <= set(domain.COUNTIES)


def test_vg_code_needs_county(world):
    _as(world, "vglead@example.org")
    vg = world.get("/api/admin/vgs/vg-a/settings").json()
    vg["tenants"] = []
    assert world.put("/api/admin/vgs/vg-a/settings", json={**vg, "bks_code": "MYK.ABC"}).status_code == 200
    assert world.put("/api/admin/vgs/vg-a/settings", json={**vg, "bks_code": "ABC"}).status_code == 422
    assert world.put("/api/admin/vgs/vg-a/settings", json={**vg, "bks_code": "MYK.ABC"}).status_code == 200
