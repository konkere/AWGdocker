#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 scripts/resolve-upstream.py --output upstream.json
mapfile -t build_args < <(python3 - <<'PY'
import json
d=json.load(open("upstream.json"))
for component in ("go", "tools"):
    for field in ("tag", "commit"):
        print("AWG_"+component.upper()+"_"+field.upper()+"="+d[component][field])
PY
)
args=()
for value in "${build_args[@]}"; do args+=(--build-arg "$value"); done
network_args=()
if [[ ${BUILD_NETWORK:-} == host ]]; then network_args+=(--network host); fi
timeout 3600 docker build --pull "${network_args[@]}" "${args[@]}" \
    --build-arg "SOURCE_URL=${SOURCE_URL:-}" \
    --build-arg "SOURCE_REVISION=${SOURCE_REVISION:-local}" \
    -t "${IMAGE:-amneziawg:local}" .
