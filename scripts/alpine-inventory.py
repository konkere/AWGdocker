#!/usr/bin/env python3
"""Record exact runtime package provenance without downloading source distfiles."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
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
            raise ValueError(f"Missing aports commit for {origin}")
        for field in ("P", "V", "L", "U", "A"):
            if not fields.get(field):
                raise ValueError(f"Missing {field} metadata for {origin}")
        result.append({"name": fields["P"], "version": fields["V"],
                       "license": fields.get("L", ""), "origin": origin,
                       "upstream_url": fields["U"], "architecture": fields["A"],
                       "aports_commit": commit})
    if not result:
        raise ValueError("Empty runtime package database")
    if len({item["name"] for item in result}) != len(result):
        raise ValueError("Duplicate runtime package")
    return sorted(result, key=lambda item: item["name"])


def run(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=600, **kwargs)


def recipe_metadata(target, commit, port, architecture):
    output = subprocess.check_output(
        ["sh", "-ec", '. ./APKBUILD; printf "%s\\0" "$pkgver-r$pkgrel" "$source"'],
        cwd=target, timeout=30, env={**os.environ, "CARCH": architecture})
    version, sources, end = output.decode().split("\0")
    base = f"https://github.com/alpinelinux/aports/blob/{commit}/{port}/"
    urls = []
    for source in sources.split():
        address = source.split("::", 1)[-1]
        if "://" in address:
            urls.append(address)
        else:
            if not (target / address).is_file():
                raise ValueError(f"Missing local recipe source: {address}")
            urls.append(base + address)
    return version, base + "APKBUILD", urls


BEGIN = "<!-- BEGIN ALPINE RUNTIME INVENTORY -->"
END = "<!-- END ALPINE RUNTIME INVENTORY -->"


def markdown(template, inventory):
    def cell(value):
        return str(value).replace("&", "&amp;").replace("<", "&lt;").replace("|", "&#124;").replace("\n", " ")
    build = inventory["build"]
    lines = [BEGIN, "", "Generated from this image's runtime APK database; build-only packages are excluded.",
             "", *(f"- {key}: `{value}`" for key, value in build.items()), "",
             "| Package | Version | License (APK metadata) | Upstream | Exact recipe | Source URLs (including patches) |",
             "| --- | --- | --- | --- | --- | --- |"]
    for package in inventory["packages"]:
        values = [package[key] for key in ("name", "version", "license", "upstream_url", "recipe_url")]
        values.append(" ; ".join(package["source_urls"]) or "No source entries in exact APKBUILD")
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(["", END])
    before, rest = template.split(BEGIN)
    previous, after = rest.split(END)
    return before + "\n".join(lines) + after


def collect(database, destination, template, revision, release):
    inventory = packages(database.read_text())
    architectures = {package["architecture"] for package in inventory} - {"noarch"}
    if len(architectures) != 1:
        raise ValueError("Expected one runtime APK architecture")
    architecture = architectures.pop()
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "installed").write_bytes(database.read_bytes())
    with tempfile.TemporaryDirectory() as temp:
        repo = Path(temp) / "aports"
        run("git", "init", "--quiet", str(repo))
        run("git", "-C", str(repo), "remote", "add", "origin",
            "https://github.com/alpinelinux/aports.git")
        # Fetch the exact commits together. Repeated shallow fetches can race
        # with Git's background maintenance updating the shallow boundary.
        commits = sorted({p["aports_commit"] for p in inventory})
        run("git", "-C", str(repo), "-c", "gc.auto=0", "-c", "maintenance.auto=false",
            "fetch", "--depth=1", "origin", *commits)
        for origin, commit in sorted({(p["origin"], p["aports_commit"])
                                       for p in inventory}):
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
            target = Path(temp) / f"{origin}-{commit}"
            target.mkdir()
            archive = Path(temp) / "recipe.tar"
            run("git", "-C", str(repo), "archive", "--format=tar",
                f"--output={archive}", commit, port)
            run("tar", "-xf", str(archive), "--strip-components=2", "-C", str(target))
            version, recipe_url, source_urls = recipe_metadata(target, commit, port, architecture)
            for package in inventory:
                if (package["origin"], package["aports_commit"]) == (origin, commit):
                    if package["version"] != version:
                        raise ValueError(f"Recipe version mismatch for {package['name']}")
                    package.update(recipe_url=recipe_url, source_urls=source_urls)
    document = {"schema_version": 1, "build": {
        "source_revision": revision, "alpine_release": release,
        "architectures": ",".join(sorted({package["architecture"] for package in inventory})),
        "installed_sha256": hashlib.sha256(database.read_bytes()).hexdigest()}, "packages": inventory}
    (destination / "packages.json").write_text(json.dumps(document, indent=2) + "\n")
    (destination / "THIRD_PARTY.md").write_text(markdown(template.read_text(), document))


def verify(database, destination, template, revision, release):
    document = json.loads((destination / "packages.json").read_text())
    expected = packages(database.read_text())
    actual = [{key: package[key] for key in expected[0]} for package in document["packages"]]
    if actual != expected or (destination / "installed").read_bytes() != database.read_bytes():
        raise ValueError("Inventory differs from installed runtime packages")
    build = document["build"]
    if (document["schema_version"] != 1 or build["source_revision"] != revision
            or build["alpine_release"] != release
            or build["architectures"] != ",".join(sorted({package["architecture"] for package in expected}))
            or build["installed_sha256"] != hashlib.sha256(database.read_bytes()).hexdigest()):
        raise ValueError("Inventory build identity mismatch")
    for package in document["packages"]:
        prefix = f"https://github.com/alpinelinux/aports/blob/{package['aports_commit']}/"
        if not package["recipe_url"].startswith(prefix) or not package["recipe_url"].endswith("/APKBUILD"):
            raise ValueError("Recipe URL is not pinned to installed commit")
        if not isinstance(package["source_urls"], list):
            raise ValueError("Missing recipe sources")
    if (destination / "THIRD_PARTY.md").read_text() != markdown(template.read_text(), document):
        raise ValueError("THIRD_PARTY.md differs from inventory")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--release", required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    action = verify if args.verify else collect
    action(args.database, args.destination, args.template, args.revision, args.release)
