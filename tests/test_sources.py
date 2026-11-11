"""Verify provenance against real temporary recipes and detect inventory drift."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inventory", ROOT / "scripts/alpine-inventory.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def record(name="libexample", version="1.2-r3", commit="a" * 40):
    return (f"P:{name}\nV:{version}\no:example\nc:{commit}\nL:GPL-2.0-only\n"
            "U:https://example.org\nA:x86_64\n")


class PackageSources(unittest.TestCase):
    def test_inventory_preserves_package_metadata(self):
        package = inventory.packages(record())[0]
        self.assertEqual((package["name"], package["version"], package["license"],
                          package["upstream_url"], package["architecture"]),
                         ("libexample", "1.2-r3", "GPL-2.0-only", "https://example.org", "x86_64"))

    def test_missing_provenance_fails_closed(self):
        for database in ("", "P:example\nV:1-r0\n", record().replace("o:example", "o:../example"),
                         record().replace("L:GPL-2.0-only", "L:"),
                         record().replace("U:https://example.org", "U:"), record() + "\n" + record()):
            with self.subTest(database=database), self.assertRaises(ValueError):
                inventory.packages(database)

    def test_exact_recipe_sources_subpackages_and_drift(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "upstream"
            recipe = repo / "main/example"
            recipe.mkdir(parents=True)
            (recipe / "APKBUILD").write_text(
                'pkgname=example\npkgver=1.2\npkgrel=3\n'
                'source="renamed.tar.gz::https://example.org/$pkgver-$CARCH.tar.gz fix.patch"\n')
            (recipe / "fix.patch").write_text("example patch\n")
            env = {**os.environ, "GIT_AUTHOR_NAME": "Konkere", "GIT_AUTHOR_EMAIL": "amorph@konkere.ru",
                   "GIT_COMMITTER_NAME": "Konkere", "GIT_COMMITTER_EMAIL": "amorph@konkere.ru"}

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], env=env, text=True)

            subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture")
            commit = git("rev-parse", "HEAD").strip()
            database = root / "installed"
            database.write_text(record("example", commit=commit) + "\n" + record(commit=commit))
            destination = root / "inventory"
            original_run = inventory.run

            def intercept(*args, **kwargs):
                if args[0] == "git" and "remote" in args:
                    args = (*args[:-1], str(repo))
                return original_run(*args, **kwargs)

            with patch.object(inventory, "run", side_effect=intercept):
                inventory.collect(database, destination, ROOT / "THIRD_PARTY.md", "fixture", "3.test")
            document = json.loads((destination / "packages.json").read_text())
            packages = document["packages"]
            self.assertEqual(len(packages), 2)
            self.assertEqual(packages[0]["source_urls"], ["https://example.org/1.2-x86_64.tar.gz",
                f"https://github.com/alpinelinux/aports/blob/{commit}/main/example/fix.patch"])
            self.assertEqual(packages[0]["source_urls"], packages[1]["source_urls"])
            self.assertEqual(sorted(path.name for path in destination.iterdir()),
                             ["THIRD_PARTY.md", "installed", "packages.json"])
            inventory.verify(database, destination, ROOT / "THIRD_PARTY.md", "fixture", "3.test")
            with self.assertRaisesRegex(ValueError, "identity"):
                inventory.verify(database, destination, ROOT / "THIRD_PARTY.md", "wrong-revision", "3.test")
            database.write_text(database.read_text().replace("1.2-r3", "1.2-r4"))
            with self.assertRaisesRegex(ValueError, "differs"):
                inventory.verify(database, destination, ROOT / "THIRD_PARTY.md", "fixture", "3.test")
            with patch.object(inventory, "run", side_effect=intercept), self.assertRaisesRegex(ValueError, "version mismatch"):
                inventory.collect(database, root / "mismatch", ROOT / "THIRD_PARTY.md", "fixture", "3.test")
            database.write_bytes((destination / "installed").read_bytes())
            (destination / "THIRD_PARTY.md").write_text("outdated table")
            with self.assertRaisesRegex(ValueError, "THIRD_PARTY"):
                inventory.verify(database, destination, ROOT / "THIRD_PARTY.md", "fixture", "3.test")

    def test_missing_local_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "APKBUILD").write_text('pkgver=1\npkgrel=0\nsource="missing.patch"\n')
            with self.assertRaisesRegex(ValueError, "Missing local"):
                inventory.recipe_metadata(root, "a" * 40, "main/example", "x86_64")


if __name__ == "__main__":
    unittest.main()
