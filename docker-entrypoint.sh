#!/bin/sh
# Startet die App unprivilegiert als Besitzer des Datenordners, damit ein vorhandener
# Ordner ./daten ohne Änderung der Dateirechte beschreibbar bleibt.
# APP_UID/APP_GID (aus .env) haben Vorrang vor dem ermittelten Besitzer.
set -eu

data="${DATA_DIR:-/daten}"

if [ "$(id -u)" != 0 ]; then
    # Bereits mit festem Benutzer gestartet (z. B. docker run --user)
    exec "$@"
fi

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

exec setpriv --reuid="$uid" --regid="$gid" --clear-groups -- "$@"
