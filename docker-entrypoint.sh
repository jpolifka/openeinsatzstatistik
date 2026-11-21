#!/bin/sh
# Startet die App unprivilegiert als Besitzer des Datenordners, damit ein vorhandener
# Ordner ./daten ohne Änderung der Dateirechte beschreibbar bleibt.
# APP_UID/APP_GID (aus .env) haben Vorrang vor dem ermittelten Besitzer.
set -eu

data="${DATA_DIR:-/daten}"

# Einsatzdaten enthalten Namen: nur der Besitzer darf lesen. Läuft als der Besitzer der Dateien (der Container hat
# kein CAP_FOWNER); bleibt danach etwas für Gruppe/andere offen oder ist etwas nicht lesbar, startet die App nicht.
harden() {
    "$@" chmod -R go-rwx "$data" 2>/dev/null || true
    if ! loose="$("$@" find "$data" -perm /077 -print -quit)" || [ -n "$loose" ]; then
        echo "Die Rechte in $data lassen sich nicht auf 'nur Besitzer' beschränken (${loose:-nicht lesbar})." \
             "Bitte den Ordner dem Benutzer geben, unter dem die App läuft (APP_UID/APP_GID), oder die Rechte" \
             "auf dem Host setzen (chmod -R go-rwx)." >&2
        exit 1
    fi
}

if [ "$(id -u)" != 0 ]; then
    # Bereits mit festem Benutzer gestartet (z. B. docker run --user)
    umask 077
    harden env
    exec "$@"
fi

umask 077
mkdir -p "$data"
uid="${APP_UID:-$(stat -c %u "$data")}"
gid="${APP_GID:-$(stat -c %g "$data")}"

if [ "$uid" = 0 ]; then
    if [ -z "$(ls -A "$data")" ]; then
        # Leerer, von Docker angelegter Ordner: dem Standardbenutzer des Images geben
        chown 10001:10001 "$data" || true
    fi
    # Docker Desktop zeigt Bind-Mounts als root-eigen, erlaubt aber das Schreiben
    if setpriv --reuid=10001 --regid=10001 --clear-groups -- test -w "$data"; then
        uid=10001
        gid=10001
    else
        echo "Datenordner $data gehört root. Bitte APP_UID/APP_GID in .env setzen" \
             "oder den Ordner einem normalen Benutzer geben – die App läuft nicht als root." >&2
        exit 1
    fi
fi

harden setpriv --reuid="$uid" --regid="$gid" --clear-groups --
exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
