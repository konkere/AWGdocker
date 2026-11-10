#!/usr/bin/env python3
"""Bundle recipes, patches and distfiles for the exact runtime Alpine packages.

Run only in the source-collection build stage, with git and abuild installed.
The runtime package database is captured before installing those build tools.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def packages(database):
    result = []
    for block in database.strip().split("\n\n"):
        fields = dict(line.split(":", 1) for line in block.splitlines()
                      if len(line) > 1 and line[1] == ":")
        if not fields:
            continue
        origin = fields.get("o", fields.get("P", ""))
        commit = fields.get("c", "")
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9+_.-]*", origin):
            raise ValueError("Invalid or missing Alpine package origin")
        if not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError(f"Missing aports commit for {origin}; cannot bundle source")
        result.append({"name": fields["P"], "version": fields["V"],
                       "license": fields.get("L", ""), "origin": origin,
                       "aports_commit": commit})
    if not result:
        raise ValueError("Empty runtime package database")
    return result


def run(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=600, **kwargs)


def collect(database, destination):
    inventory = packages(database.read_text())
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "packages.json").write_text(json.dumps(inventory, indent=2) + "\n")
    shutil.copyfile(database, destination / "installed")
    with tempfile.TemporaryDirectory() as temp:
        repo = Path(temp) / "aports"
        run("git", "init", "--quiet", str(repo))
        run("git", "-C", str(repo), "remote", "add", "origin",
            "https://github.com/alpinelinux/aports.git")
        fetched = set()
        for origin, commit in sorted({(p["origin"], p["aports_commit"])
                                       for p in inventory}):
            if commit not in fetched:
                run("git", "-C", str(repo), "fetch", "--depth=1", "origin", commit)
                fetched.add(commit)
            port = None
            for section in ("main", "community", "testing"):
                candidate = f"{section}/{origin}"
                found = subprocess.run(["git", "-C", str(repo), "cat-file", "-e",
                                        f"{commit}:{candidate}/APKBUILD"],
                                       capture_output=True, timeout=10)
                if found.returncode == 0:
                    port = candidate
                    break
            if port is None:
                raise RuntimeError(f"No recipe for {origin} at {commit}")
            target = destination / f"{origin}-{commit}"
            target.mkdir()
            archive = Path(temp) / "recipe.tar"
            run("git", "-C", str(repo), "archive", "--format=tar",
                f"--output={archive}", commit, port)
            run("tar", "-xf", str(archive), "--strip-components=2", "-C", str(target))
            distfiles = target / "distfiles"
            distfiles.mkdir()
            # abuild fetch verifies the checksums from the original APKBUILD.
            run("abuild", "-F", "fetch", cwd=target,
                env={**os.environ, "SRCDEST": str(distfiles)})
            (target / "APORTS_COMMIT").write_text(commit + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    collect(args.database, args.destination)
