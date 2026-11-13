"""Offline regression tests. No Docker daemon, network or production keys."""
import importlib.util
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resolver", ROOT / "scripts/resolve-upstream.py")
resolver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resolver)

class Tags(unittest.TestCase):
    def test_numeric_order_annotated_and_prerelease(self):
        a, b, c = ("a" * 40, "b" * 40, "c" * 40)
        refs = (f"{a}\trefs/tags/v3.9.20260101\n"
                f"{b}\trefs/tags/v3.10.20260101\n"
                f"{c}\trefs/tags/v3.10.20260101^{{}}\n"
                f"{a}\trefs/tags/v4.0.0-rc1\n")
        self.assertEqual(resolver.select_tag(refs),
                         {"tag": "v3.10.20260101", "commit": c})

    def test_missing_stable_tag_fails(self):
        with self.assertRaises(ValueError):
            resolver.select_tag("a" * 40 + "\trefs/tags/v4.0.0-beta1\n")

class ShellTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.bin = self.path / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"],
                    "TMPDIR": str(self.path), "AWG_TEST_DIR": str(self.path)}

    def script(self, name, body):
        file = self.bin / name
        file.write_text("#!/bin/bash\nset -euo pipefail\n" + body)
        file.chmod(0o755)

class Generator(ShellTests):
    def setUp(self):
        super().setUp()
        self.script("docker", "printf '%043d=\\n' 0\n")
        self.env.update(AWG_IMAGE="example:test", ENDPOINT="203.0.113.10:443")

    def run_generator(self, output="private-configs"):
        return subprocess.run(["bash", str(ROOT / "scripts/generate-example.sh"), output],
                              cwd=self.path, env=self.env, capture_output=True, text=True,
                              timeout=5)

    def test_permissions_and_no_overwrite(self):
        self.assertEqual(self.run_generator().returncode, 0)
        target = self.path / "private-configs/server/awg0.conf"
        before = target.read_bytes()
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        self.assertEqual(target.parent.stat().st_mode & 0o777, 0o700)
        self.assertNotEqual(self.run_generator().returncode, 0)
        self.assertEqual(target.read_bytes(), before)

    def test_rejects_endpoint_newline(self):
        self.env["ENDPOINT"] = "server:443\nPostUp = injected"
        self.assertNotEqual(self.run_generator().returncode, 0)
        self.assertFalse((self.path / "private-configs").exists())

    def test_rejects_invalid_port(self):
        self.env["ENDPOINT"] = "server:65536"
        self.assertNotEqual(self.run_generator().returncode, 0)

    def test_ipv6_endpoint(self):
        self.env["ENDPOINT"] = "[2001:db8::1]:443"
        self.assertEqual(self.run_generator().returncode, 0)

class Lifecycle(ShellTests):
    def setUp(self):
        super().setUp()
        self.source = self.path / "source.conf"
        self.source.write_text("before\n")
        self.env["AWG_CONFIG_FILE"] = str(self.source)
        self.script("awg-quick", r'''
printf '%s ' "$1" >> "$AWG_TEST_DIR/calls"
cat "$2" >> "$AWG_TEST_DIR/calls"
if [[ $1 == up ]]; then exit "${AWG_TEST_UP_EXIT:-0}"; fi
exit "${AWG_TEST_DOWN_EXIT:-0}"
''')
        self.script("awg", r'''
touch "$AWG_TEST_DIR/ready"
exit "${AWG_TEST_PROBE_EXIT:-0}"
''')

    def start(self):
        proc = subprocess.Popen(["bash", str(ROOT / "entrypoint.sh")], env=self.env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        def stop():
            if proc.poll() is None:
                proc.kill()
            proc.wait(timeout=3)
        self.addCleanup(stop)
        return proc

    def wait_ready(self, proc, marker="ready"):
        for _ in range(100):
            if (self.path / marker).exists():
                return
            if proc.poll() is not None:
                self.fail("Entrypoint exited before ready")
            time.sleep(.01)
        self.fail("Entrypoint did not become ready")

    def calls(self):
        return (self.path / "calls").read_text().splitlines()

    def test_term_uses_startup_snapshot(self):
        proc = self.start()
        self.wait_ready(proc)
        self.source.write_text("changed\n")
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=3), 0)
        self.assertEqual(self.calls(), ["up before", "down before"])
        self.assertEqual(list(self.path.glob("tmp*")), [])

    def test_cleanup_failure_is_not_success(self):
        self.env["AWG_TEST_DOWN_EXIT"] = "7"
        proc = self.start()
        self.wait_ready(proc)
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=3), 1)

    def test_term_does_not_wait_for_unresponsive_timer(self):
        # Model a timer that cannot act on TERM during child startup.
        self.script("sleep", r'''
trap '' TERM
touch "$AWG_TEST_DIR/sleep-ready"
exec /bin/sleep "$@"
''')
        proc = self.start()
        self.wait_ready(proc, "sleep-ready")
        proc.send_signal(signal.SIGTERM)
        self.assertEqual(proc.wait(timeout=3), 0)
        self.assertEqual(self.calls(), ["up before", "down before"])
        self.assertEqual(list(self.path.glob("tmp*")), [])

    def test_daemon_loss_is_not_success(self):
        self.env["AWG_TEST_PROBE_EXIT"] = "1"
        proc = self.start()
        self.assertEqual(proc.wait(timeout=3), 1)
        self.assertEqual(self.calls(), ["up before", "down before"])

    def test_start_failure_keeps_exit_status(self):
        self.env["AWG_TEST_UP_EXIT"] = "9"
        proc = self.start()
        self.assertEqual(proc.wait(timeout=3), 9)
        self.assertEqual(self.calls(), ["up before"])

class UserspaceOverride(unittest.TestCase):
    def test_kernel_creator_is_bypassed(self):
        # Simulate upstream's hook: the late definition must replace the first one.
        content = ('add_if() { echo kernel; }\n'
                   + (ROOT / "scripts/quick-userspace.bash").read_text()
                   + '\ncmd() { printf "%s\\n" "$*"; }\nINTERFACE=awg0\nadd_if\n')
        out = subprocess.check_output(["bash"], input=content, text=True)
        self.assertEqual(out, "amneziawg-go awg0\n")

if __name__ == "__main__":
    unittest.main()
