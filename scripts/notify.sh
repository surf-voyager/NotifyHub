#!/usr/bin/env sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
exec "${NOTIFYHUB_PYTHON:-python3}" "$project_root/client/notify.py" "$@"
