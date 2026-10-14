"""Ein gemeinsamer Feldkatalog für API, Speicherung und Einsatzformular."""
FIELDS = ("number", "started_at", "ended_at", "keyword", "subcode", "description", "place",
          "unit_leader", "station_staff", "dispatch_number", "abort_reason")
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
]
