# -*- coding: utf-8 -*-
from app.names import NameMatcher, normalize, short_name, split_name


def test_normalize():
    assert normalize("Groß-Müller") == "grossmuller"


def test_short_name():
    assert short_name("Max", "Muster") == "M. Muster"
    assert short_name("Christa", "Muster") == "Ch. Muster"


def test_split_name():
    assert split_name("Muster, Max") == ("Muster", "Max")
    assert split_name("Max  Muster") == ("Muster", "Max")
    assert split_name("Muster") == ("Muster", "")


def test_matcher():
    matcher = NameMatcher([(1, "Muster, Max"), (2, "Muster, Erika"), (3, "Beispiel Anna")])
    assert matcher.match("Muster", "Erika") == 2
    assert matcher.match("Beispiel", "Anna") == 3        # "Nachname Vorname" ohne Komma
    assert matcher.match("Anna", "Beispiel") == 3        # vertauscht
    assert matcher.match("Mustre", "Max") == 1           # Tippfehler
    assert matcher.match("Unbekannt", "Otto") is None
