#!/usr/bin/env sh
set -eu
project_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python_executable=${NOTIFYHUB_PYTHON:-python3}
client_script=$project_root/client/notify.py
case "$python_executable" in
    *.exe)
        if ! command -v wslpath >/dev/null 2>&1; then
            echo "Windows Python requires wslpath; otherwise use python3" >&2
            exit 2
        fi
        client_script=$(wslpath -w "$client_script")
        ;;
esac
exec "$python_executable" "$client_script" "$@"
