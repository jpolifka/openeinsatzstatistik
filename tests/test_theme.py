# -*- coding: utf-8 -*-
import dataclasses
import random

import pytest

from app import db, tenancy, theme
from conftest import CFG, grant, login, make_tenant

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 20


@pytest.mark.parametrize("brand", ["#D90000", "#004B8D", "#1B5E20", "#5E35B1", "#C62828", "#37506B", "#8A6D00"])
def test_palette_keeps_text_and_charts_readable(brand):
    p = theme.palette({"brand": brand})
    for token in ("--brand", "--brand-dark", "--brand-mid"):
        assert theme.contrast(p[token], "#FFFFFF") >= theme.MIN_TEXT_CONTRAST or token == "--brand"
    assert theme.contrast(p["--brand-accent"], "#FFFFFF") >= theme.MIN_CHART_CONTRAST
    assert not {"--series", "--day", "--night"} & set(p)      # Diagrammreihen sind neutral und gehören nicht zum Theme
    assert theme.contrast(p["--brand-dark"], "#FFFFFF") >= 7


def test_palette_for_random_valid_colors():
    rng = random.Random(1)
    for _ in range(300):
        brand = "#" + "".join(f"{rng.randrange(256):02X}" for _ in range(3))
        if theme.check({"brand": brand}):
            continue
        p = theme.palette({"brand": brand})
        assert theme.contrast(p["--brand-mid"], "#FFFFFF") >= theme.MIN_TEXT_CONTRAST, brand
        assert theme.contrast(p["--brand-accent"], "#FFFFFF") >= theme.MIN_CHART_CONTRAST, brand


def test_check_and_normalize():
    assert theme.check({"brand": "#D90000", "brand_dark": "#7A0000"}) == []
    assert theme.check(theme.NEUTRAL) == []
    problems = theme.check({"brand": "#FFD700"})
    assert len(problems) == 1 and "1,4:1" in problems[0] and "4,5:1" in problems[0]
    assert theme.normalize({"brand": "#d90000", "brand_dark": ""}) == {"brand": "#D90000"}
    for bad in ("red", "#D9000", "#D90000;}body{display:none", "#GGGGGG", 12):
        with pytest.raises(ValueError):
            theme.normalize({"brand": bad})
    with pytest.raises(ValueError):
        theme.normalize({"brand_dark": "#7A0000"})
    assert theme.css({}) == "" and theme.css({"brand": "#004B8D"}).startswith(":root{--brand:#004B8D;")


def test_image_type_by_content():
    assert theme.image_type(PNG) == "image/png"
    assert theme.image_type(b"\xff\xd8\xff\xe0" + b"0" * 10) == "image/jpeg"
    assert theme.image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert theme.image_type(b"<svg onload='alert(1)'>") is None
    assert theme.image_type(b"GIF89a") is None


@pytest.fixture
def branded(make_client):
    vg_id, a1 = make_tenant("wehr-a1", "vg-a", cfg=dataclasses.replace(CFG, colors={"brand": "#004B8D"}))
    _, b1 = make_tenant("wehr-b1", "vg-b")
    with db.connection(tenancy.tenant_path("wehr-a1")) as con:
        con.execute("INSERT INTO asset (name, content_type, data) VALUES ('logo-light', 'image/png', ?)", (PNG,))
    grant("lead@example.org", "lead", a1)
    grant("vglead@example.org", "vg_lead", vg_id)
    return make_client(login=True)


def test_theme_and_logos_follow_the_selection(branded):
    login(branded, "lead@example.org")
    assert branded.get("/api/theme.css").text.startswith(":root{--brand:#004B8D;")
    branding = branded.get("/api/config").json()["branding"]
    assert branding["logo_light"].startswith("/api/branding/wehr-a1/logo-light?v=")
    assert branding["logo_dark"] is None and branding["icon"] is None
    logo = branded.get(branding["logo_light"])
    assert logo.content == PNG and logo.headers["content-type"] == "image/png"
    assert logo.headers["x-content-type-options"] == "nosniff" and "sandbox" in logo.headers["content-security-policy"]
    # Logo einer fremden Wehr: kein Zugriff
    assert branded.get("/api/branding/wehr-b1/logo-light").status_code == 403
    assert branded.get("/api/branding/wehr-a1/logo-dark").status_code == 404


def test_vg_view_and_login_page_are_neutral(branded):
    login(branded, "vglead@example.org")
    assert branded.get("/api/config").json()["vg"]
    assert branded.get("/api/theme.css").text == theme.css(theme.NEUTRAL)
    assert branded.get("/api/config").json()["branding"] == {"logo_light": None, "logo_dark": None, "icon": None}
    branded.cookies.clear()
    page = branded.get("/login").text
    assert theme.NEUTRAL["brand"] in page and "Altenau" not in page


def test_tenant_without_colors_keeps_default_theme(make_client):
    make_tenant("wehr-a1")
    assert make_client().get("/api/theme.css").text == ""


def test_font_type_and_css():
    woff2 = b"wOF2" + b"\x00\x01\x00\x00" + (64).to_bytes(4, "big") + b"\x00" * 52
    assert theme.font_type(woff2) == "font/woff2"
    assert theme.font_type(woff2.replace(b"wOF2", b"wOFF")) == "font/woff"
    assert theme.font_type(woff2[:63]) is None and theme.font_type(b"") is None
    assert theme.font_type(b"OTTO" + b"\x00" * 20) == "font/otf"
    assert theme.font_type(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20) is None
    css = theme.css({}, [("font", "/api/branding/x/font?v=1", "font/woff2")])
    assert css.startswith('@font-face{font-family:"Wehrschrift"') and 'url("/api/branding/x/font?v=1")' in css
    assert theme.SYSTEM_FONT in css
    assert theme.css({}, []) == "" and theme.css({}, [("font", "/x", "text/html")]) == ""
