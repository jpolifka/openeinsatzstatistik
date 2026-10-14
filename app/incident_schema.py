"""Ein gemeinsamer Feldkatalog für API, Speicherung und Einsatzformular."""
# Angaben, die nur der BKS-Bericht liefert: leer heißt „nicht angegeben“ (nie null Personen, null Minuten)
OPTIONAL_TEXT = ("building", "alarm_system", "tactic")
OPTIONAL_TIMES = ("fire_controlled_at", "fire_out_at", "fire_watch_until")
OPTIONAL_COUNTS = ("rescued", "rescued_animals", "injured", "injured_firefighters", "deceased")
FIELDS = ("number", "started_at", "ended_at", "keyword", "subcode", "description", "place",
          "unit_leader", "station_staff", "dispatch_number", "abort_reason",
          *OPTIONAL_TEXT, *OPTIONAL_TIMES, *OPTIONAL_COUNTS)
INT_FIELDS = ("number", "station_staff")
FORM_FIELDS = [
    ["number", "Nr.", "number", "", 'min="0"'],
    ["started_at", "Beginn", "datetime-local", "span-2", 'step="1"'],
    ["ended_at", "Ende", "datetime-local", "span-2", 'step="1"'],
    ["station_staff", "Gerätehaus", "number", "", 'min="0"'],
    ["keyword", "Stichwort", "text", "", 'placeholder="Suche" autocomplete="off" role="combobox" aria-autocomplete="list"'],
    ["subcode", "Stufe", "text", "", 'maxlength="2"'],
    ["description", "Einsatz", "text", "span-4", ""],
    ["place", "Ort", "text", "span-3", 'list="place-options"'],
    ["unit_leader", "Einheitsführung", "text", "span-3", 'list="leader-options" placeholder="z. B. M. Muster"'],
    ["dispatch_number", "Leitstellen-Nr.", "text", "span-2", ""],
    ["abort_reason", "Einsatzabbruch", "text", "span-4", 'placeholder="leer = kein Abbruch"'],
    ["building", "Objekt", "text", "span-2", 'placeholder="z. B. Pflegeheim"'],
    ["alarm_system", "Brandmelde-Nr.", "text", "span-2", 'placeholder="Nr. der Anlage"'],
    ["tactic", "Einsatztaktik", "text", "span-2", 'placeholder="Innen-/Außenangriff"'],
    ["fire_controlled_at", "Brand unter Kontrolle", "datetime-local", "span-2", 'step="60"'],
    ["fire_out_at", "Feuer aus", "datetime-local", "span-2", 'step="60"'],
    ["fire_watch_until", "Brandwache bis", "datetime-local", "span-2", 'step="60"'],
    ["rescued", "Menschen gerettet", "number", "", 'min="0"'],
    ["rescued_animals", "Tiere gerettet", "number", "", 'min="0"'],
    ["injured", "Verletzte", "number", "", 'min="0"'],
    ["injured_firefighters", "Verletzte FW", "number", "", 'min="0"'],
    ["deceased", "Verstorbene", "number", "", 'min="0"'],
]
