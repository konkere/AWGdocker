"""Verify source provenance parsing and collection against a temporary Git repo."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bundle", ROOT / "scripts/bundle-alpine-sources.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class PackageSources(unittest.TestCase):
    def test_inventory_preserves_versions_origin_and_license(self):
        text = "P:libexample\nV:1.2-r3\no:example\nc:" + "a" * 40 + "\nL:GPL-2.0-only\n"
        p = bundle.packages(text)[0]
        self.assertEqual((p["name"], p["version"], p["origin"], p["license"]),
                         ("libexample", "1.2-r3", "example", "GPL-2.0-only"))

    def test_missing_provenance_fails_closed(self):
        for text in ("", "P:example\nV:1-r0\n", "P:../example\nV:1-r0\nc:" + "a" * 40):
            with self.subTest(text=text), self.assertRaises(ValueError):
                bundle.packages(text)

    def test_full_recipe_collection_and_subpackage_deduplication(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            repo = root / "upstream"
            recipe = repo / "main/example"
            recipe.mkdir(parents=True)
            (recipe / "APKBUILD").write_text("pkgname=example\npkgver=1\npkgrel=0\n")
            (recipe / "fix.patch").write_text("example patch\n")
            env = {**os.environ, "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.invalid",
                   "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.invalid"}
            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], env=env, text=True)
            subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
            git("add", ".")
            git("-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "Fixture")
            commit = git("rev-parse", "HEAD").strip()
            database = root / "installed"
            database.write_text("\n\n".join(f"P:{name}\nV:1-r0\no:example\nc:{commit}\nL:MIT"
                                           for name in ("example", "libexample")))
            destination = root / "sources"
            original_run = bundle.run
            fetched = []
            def intercept(*args, **kwargs):
                if args[0] == "git" and "remote" in args:
                    args = (*args[:-1], str(repo))
                if args[0] == "abuild":
                    fetched.append(Path(kwargs["cwd"]))
                    Path(kwargs["env"]["SRCDEST"], "example.tar.gz").write_bytes(b"fixture source")
                    return
                return original_run(*args, **kwargs)
            with patch.object(bundle, "run", side_effect=intercept):
                bundle.collect(database, destination)
            self.assertEqual(len(fetched), 1)
            self.assertTrue((fetched[0] / "fix.patch").is_file())
            self.assertTrue((fetched[0] / "distfiles/example.tar.gz").is_file())
            self.assertEqual(len(json.loads((destination / "packages.json").read_text())), 2)


if __name__ == "__main__":
    unittest.main()
