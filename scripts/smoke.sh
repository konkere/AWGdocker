#!/bin/bash
# Disposable AWG-to-AWG integration test; never use production keys.
set -euo pipefail
image=${1:?Usage: smoke.sh IMAGE}
mode=${SMOKE_MODE:-advanced}
[[ $mode == basic || $mode == advanced ]] || { echo "Invalid SMOKE_MODE" >&2; exit 1; }
prefix="awg-test-${RANDOM}-$$"
work=$(mktemp -d)
chmod 700 "$work"
cleanup() {
    docker rm -f "$prefix-client" "$prefix-server" >/dev/null 2>&1 || true
    docker network rm "$prefix-net" >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT
umask 077
awg() { timeout 20 docker run --rm -i --entrypoint awg "$image" "$@"; }
server_private=$(awg genkey)
server_public=$(printf '%s\n' "$server_private" | awg pubkey)
client_private=$(awg genkey)
client_public=$(printf '%s\n' "$client_private" | awg pubkey)
psk=$(awg genpsk)
hpk=$(awg genkey)
obfs="Jc = 3
Jmin = 64
Jmax = 300
S1 = 100
S2 = 120
S3 = 32
S4 = 24
H1 = 1000001-1000011
H2 = 1000101-1000111
H3 = 1000201-1000211
H4 = 1000301-1000311
HeaderProtectionKey = $hpk"
extra=
if [[ $mode == advanced ]]; then
    obfs+=$'\nRandomTrailers = on\nContentPaddingAddition = 16-160'
    extra='I1 = <b 0xc30000000108><r 8><b 0x000044d0><r 1200>'
fi
cat > "$work/server.conf" <<EOF
[Interface]
PrivateKey = $server_private
Address = 10.203.0.1/32
ListenPort = 51820
MTU = 1280
$obfs
PostDown = touch /test-results/server-stopped

[Peer]
PublicKey = $client_public
PresharedKey = $psk
AllowedIPs = 10.203.0.2/32
EOF
docker network create "$prefix-net" >/dev/null
docker run -d --name "$prefix-server" --network "$prefix-net" \
    --cap-add NET_ADMIN --device /dev/net/tun \
    --mount "type=bind,src=$work/server.conf,dst=/etc/amnezia/amneziawg/awg0.conf,readonly" \
    --mount "type=bind,src=$work,dst=/test-results" \
    "$image" >/dev/null
server_ip=$(docker inspect "$prefix-server" --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}')
cat > "$work/client.conf" <<EOF
[Interface]
PrivateKey = $client_private
Address = 10.203.0.2/32
MTU = 1280
$obfs
$extra
PostDown = touch /test-results/client-stopped

[Peer]
PublicKey = $server_public
PresharedKey = $psk
Endpoint = $server_ip:51820
AllowedIPs = 0.0.0.0/0
PersistentKeepalive = 25
EOF
docker run -d --name "$prefix-client" --network "$prefix-net" \
    --cap-add NET_ADMIN --device /dev/net/tun \
    --sysctl net.ipv4.conf.all.src_valid_mark=1 \
    --sysctl net.ipv6.conf.all.disable_ipv6=1 \
    --mount "type=bind,src=$work/client.conf,dst=/etc/amnezia/amneziawg/awg0.conf,readonly" \
    --mount "type=bind,src=$work,dst=/test-results" \
    "$image" >/dev/null
success=0
for _ in $(seq 1 20); do
    if timeout 6 docker exec "$prefix-client" ping -c1 -W2 10.203.0.1 >/dev/null 2>&1; then
        success=1
        break
    fi
    sleep 2
done
if (( ! success )); then
    docker inspect --format '{{.Name}} {{.State.Status}} {{.State.ExitCode}}' \
        "$prefix-client" "$prefix-server"
    echo "AWG smoke test failed" >&2
    exit 1
fi
timeout 10 docker exec "$prefix-server" ping -c3 -W2 10.203.0.2
timeout 10 docker exec "$prefix-client" awg show awg0 latest-handshakes
docker stop --time 30 "$prefix-client" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$prefix-client")" = 0
test -f "$work/client-stopped"
docker stop --time 30 "$prefix-server" >/dev/null
test "$(docker inspect --format '{{.State.ExitCode}}' "$prefix-server")" = 0
test -f "$work/server-stopped"
echo "AWG $mode: handshake, bidirectional ping and both down hooks passed"
