#!/bin/bash
set -Eeuo pipefail
interface=awg0
started=0
sleeper=
runtime_dir=
config=
cleanup() {
    local status=$?
    trap - EXIT TERM INT
    if [[ -n $sleeper ]]; then
        kill "$sleeper" 2>/dev/null || true
        wait "$sleeper" 2>/dev/null || true
    fi
    if (( started )); then
        if ! timeout 20 awg-quick down "$config"; then
            echo "AWG cleanup failed; inspect interface, routes and hook rules before restarting" >&2
            status=1
        fi
    fi
    if [[ -n $config ]]; then rm -f -- "$config"; fi
    if [[ -n $runtime_dir ]]; then rmdir -- "$runtime_dir" || true; fi
    exit "$status"
}
trap cleanup EXIT
trap 'exit 0' TERM INT
umask 077
# Keep the exact config used at startup for down, even if the bind source changes.
runtime_dir=$(mktemp -d)
config="$runtime_dir/$interface.conf"
cp -- "${AWG_CONFIG_FILE:-/etc/amnezia/amneziawg/awg0.conf}" "$config"
chmod 600 "$config"
awg-quick up "$config"
started=1
while true; do
    timeout 5 awg show "$interface" listen-port >/dev/null || exit 1
    sleep 10 &
    sleeper=$!
    wait "$sleeper"
    sleeper=
done
