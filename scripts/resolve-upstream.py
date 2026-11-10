#!/usr/bin/env python3
"""Resolve newest numeric stable Git tags once, including peeled commit IDs."""
import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

REPOSITORIES = {
    "go": "https://github.com/amnezia-vpn/amneziawg-go.git",
    "tools": "https://github.com/amnezia-vpn/amneziawg-tools.git",
}

def select_tag(output):
    refs = {}
    for line in output.splitlines():
        sha, ref = line.split()
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise ValueError("Unexpected Git object ID")
        refs[ref] = sha
    candidates = []
    for ref in refs:
        match = re.fullmatch(r"refs/tags/(v?(\d+(?:\.\d+)+))", ref)
        if match:
            candidates.append((tuple(map(int, match[2].split("."))), match[1], ref))
    if not candidates:
        raise ValueError("No numeric stable tags found; refusing a branch fallback")
    _, tag, ref = max(candidates)
    return {"tag": tag, "commit": refs.get(ref + "^{}", refs[ref])}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="upstream.json")
    args = parser.parse_args()
    data = {}
    for name, url in REPOSITORIES.items():
        result = subprocess.run(
            ["git", "ls-remote", "--tags", url], text=True,
            capture_output=True, timeout=45, check=True,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        data[name] = {**select_tag(result.stdout), "repository": url}
    data["fingerprint"] = hashlib.sha256(
        json.dumps(data, sort_keys=True).encode()
    ).hexdigest()[:24]
    Path(args.output).write_text(json.dumps(data, indent=2) + "\n")
    print(json.dumps(data, indent=2))

if __name__ == "__main__":
    main()
