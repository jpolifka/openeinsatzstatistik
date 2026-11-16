# Mitmachen

Willkommen, besonders aus anderen Wehren und Verbandsgemeinden.

- **Fehler und Wünsche:** als Issue, mit Beschreibung, was erwartet wurde und was passiert ist.
  **Keine echten Berichte, Namen oder Screenshots mit Personendaten** anhängen. Beispiele erfinden („M. Muster“).
- **Neue Berichtsformate** (anderes Bundesland, geänderter BKS-Export): ein anonymisiertes Beispiel hilft am meisten;
  den Parser ergänzen wir dann mit Tests (`app/pdf_report.py`, `app/xlsx_report.py`).
- **Code:** Sprachkonvention und Architektur stehen in [CLAUDE.md](CLAUDE.md) und im README
  (Code englisch, Kommentare und Oberfläche deutsch). Gearbeitet wird mit Docker:

  ```bash
  docker build --target test -t openeinsatzstatistik-test . && docker run --rm openeinsatzstatistik-test
  docker run --rm -v "$PWD:/w:ro" -w /w node:22-alpine node --test tests/frontend/*.test.cjs
  ```

  Neue Endpunkte mit Einsatzdaten gehören in die Rechte-Matrix (`tests/test_access.py`).
- Mit einem Beitrag stimmst du zu, dass er unter der GNU Affero General Public License 3.0 steht (wie das Projekt).
