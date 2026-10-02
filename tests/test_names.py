# -*- coding: utf-8 -*-
import pytest

from app.names import NameMatcher, leader_spelling, matches_leader, normalize, short_name, split_name


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
    assert matcher.match("Muster", "M.") == 1            # Initiale


def test_matcher_keeps_relatives_and_swapped_names_apart():
    matcher = NameMatcher([(1, "Muster, Max"), (2, "Thomas, Tim")])
    assert matcher.match("Muster", "Moritz") is None     # gleicher Nachname, anderer Vorname
    assert matcher.match("Muster", "Mia") is None        # auch nicht über die Ähnlichkeit des ganzen Namens
    assert matcher.match("Werner", "Thomas") is None     # Vorname Thomas ist nicht Nachname Thomas
    assert matcher.match("Thomas", "Tim") == 2


@pytest.mark.parametrize("text", ["M. Muster", "Ma. Muster", "Muster, M.", "Max Muster", "Muster Max", "Muster",
                                  "MUSTER, MAX"])
def test_leader_matches_different_conventions(text):
    assert matches_leader(text, "Muster", "Max")
    assert matches_leader(text, "Muster-Beispiel", "Max")   # Doppelname: ein Namensteil reicht
    assert matches_leader("Ch. Beispiel", "Beispiel", "Christian")


@pytest.mark.parametrize("text", ["E. Muster", "Erika Muster", "M. Mustermann", "", "Beispiel"])
def test_leader_does_not_match_others(text):
    assert not matches_leader(text, "Muster", "Max")


def test_leader_spelling_prefers_known_spelling():
    spellings = {"Muster, M.": 3, "M. Muster": 1, "Ch. Beispiel": 2}
    assert leader_spelling(spellings, "Muster", "Max") == "Muster, M."
    assert leader_spelling(spellings, "Muster", "Erika") == "E. Muster"
    assert leader_spelling({}, "Beispiel", "Christa") == "Ch. Beispiel"
    assert leader_spelling({}, "Beispiel", "") == "Beispiel"
