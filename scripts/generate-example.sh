#!/bin/bash
# Run on a trusted machine. Files contain private keys; do not commit them.
set -euo pipefail
: "${AWG_IMAGE:?Set AWG_IMAGE to the selected image reference}"
: "${ENDPOINT:?Set ENDPOINT to the server address and UDP port}"
if [[ ! $ENDPOINT =~ ^([[:alnum:]_.-]+|\[[[:xdigit:]:.]+\]):([0-9]{1,5})$ ]]; then
    echo "ENDPOINT must be host:port or [IPv6]:port" >&2
    exit 1
fi
port=${BASH_REMATCH[2]}
(( 10#$port > 0 && 10#$port <= 65535 )) || { echo "Invalid UDP port" >&2; exit 1; }
out=${1:-./private-configs}
umask 077
# A fresh directory prevents accidental overwrite of an existing peer pair.
mkdir -m 700 -- "$out"
mkdir -m 700 -- "$out/server" "$out/client"
set -C
awg() { timeout 20 docker run --rm -i --entrypoint awg "$AWG_IMAGE" "$@"; }
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
cat > "$out/server/awg0.conf" <<EOF
[Interface]
PrivateKey = $server_private
Address = 10.203.0.1/32
ListenPort = 443
MTU = 1280
$obfs

[Peer]
PublicKey = $client_public
PresharedKey = $psk
AllowedIPs = 10.203.0.2/32
EOF
cat > "$out/client/awg0.conf" <<EOF
[Interface]
PrivateKey = $client_private
Address = 10.203.0.2/32
MTU = 1280
$obfs

[Peer]
PublicKey = $server_public
PresharedKey = $psk
Endpoint = $ENDPOINT
AllowedIPs = 10.203.0.1/32
PersistentKeepalive = 25
EOF
echo "Created two private configs under $out"
