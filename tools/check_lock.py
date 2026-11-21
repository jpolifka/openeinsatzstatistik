"""Prüft, dass requirements.lock jede in requirements.txt festgelegte Version enthält (CI, kein Neuaufbau)."""
import re
import sys


def pins(path):
    found = {}
    for line in open(path, encoding="utf-8"):
        m = re.match(r"([A-Za-z0-9_.-]+)(?:\[[^\]]*\])?==([^\s;\\]+)", line.strip())
        if m:
            found[m.group(1).lower().replace("_", "-")] = m.group(2)
    return found


wanted, locked = pins("requirements.txt"), pins("requirements.lock")
wrong = {name: (version, locked.get(name)) for name, version in wanted.items() if locked.get(name) != version}
for name, (want, have) in wrong.items():
    print(f"{name}: requirements.txt verlangt {want}, der Lock enthält {have}")
if wrong:
    sys.exit("requirements.lock ist nicht aktuell – neu erzeugen (siehe CLAUDE.md/README).")
print(f"Lock stimmt mit requirements.txt überein ({len(wanted)} Pakete).")
