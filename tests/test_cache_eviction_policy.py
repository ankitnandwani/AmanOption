"""Regression tests for the local cache eviction policy.

The local cache is the only place where downloaded market data lives before the
R2 migration, so it must never delete data unless the owner explicitly asks for
a size limit. These tests pin that behaviour down.
"""

import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_in_subprocess(code: str, env_overrides: dict) -> str:
    """Run a snippet in a fresh interpreter so module-level env reads are honoured."""
    env = dict(os.environ)
    for key in ("MAX_CACHE_SIZE_MB", "RENDER"):
        env.pop(key, None)
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )
    if result.returncode != 0:
        raise AssertionError(f"subprocess failed:\n{result.stdout}\n{result.stderr}")
    return result.stdout


_SETUP = """
import pathlib, sys, tempfile, time
sys.path.insert(0, {repo!r})
import services.historical_service as hs

tmp = pathlib.Path(tempfile.mkdtemp())
for i in range(5):
    p = tmp / ("2025-01-0%d.pkl" % (i + 1))
    p.write_bytes(b"x" * 400000)
    time.sleep(0.01)
hs.CACHE_DIR = tmp
"""


class TestCacheEvictionPolicy(unittest.TestCase):
    """The limit resolution rules."""

    def _resolve(self, env_overrides: dict) -> int:
        code = (
            _SETUP.format(repo=str(REPO_ROOT))
            + "print('RESULT', hs.MAX_CACHE_SIZE_MB, hs.CACHE_EVICTION_ENABLED)\n"
        )
        out = _run_in_subprocess(code, env_overrides)
        value = out.split("RESULT")[1].split()
        return int(value[0]), value[1] == "True"

    def test_local_default_is_unlimited(self):
        """Without configuration a development machine must never delete data."""
        limit, enabled = self._resolve({})
        self.assertEqual(limit, 0)
        self.assertFalse(enabled)

    def test_explicit_zero_means_unlimited(self):
        """MAX_CACHE_SIZE_MB=0 disables eviction (it must not mean 'delete all')."""
        limit, enabled = self._resolve({"MAX_CACHE_SIZE_MB": "0"})
        self.assertEqual(limit, 0)
        self.assertFalse(enabled)

    def test_negative_means_unlimited(self):
        limit, enabled = self._resolve({"MAX_CACHE_SIZE_MB": "-1"})
        self.assertEqual(limit, -1)
        self.assertFalse(enabled)

    def test_explicit_limit_is_honoured(self):
        limit, enabled = self._resolve({"MAX_CACHE_SIZE_MB": "250"})
        self.assertEqual(limit, 250)
        self.assertTrue(enabled)

    def test_render_defaults_to_bounded_cache(self):
        """Render's filesystem is ephemeral, so the deployed service stays bounded."""
        limit, enabled = self._resolve({"RENDER": "true"})
        self.assertEqual(limit, 500)
        self.assertTrue(enabled)

    def test_explicit_limit_overrides_render_default(self):
        limit, enabled = self._resolve({"RENDER": "true", "MAX_CACHE_SIZE_MB": "128"})
        self.assertEqual(limit, 128)
        self.assertTrue(enabled)

    def test_invalid_value_falls_back_to_unlimited(self):
        limit, enabled = self._resolve({"MAX_CACHE_SIZE_MB": "not-a-number"})
        self.assertEqual(limit, 0)
        self.assertFalse(enabled)


class TestCacheEvictionBehaviour(unittest.TestCase):
    """What the eviction function actually does to files."""

    def _run_eviction(self, limit_bytes: int, enabled: bool) -> str:
        code = (
            _SETUP.format(repo=str(REPO_ROOT))
            + f"""
hs.MAX_CACHE_SIZE_BYTES = {limit_bytes}
hs.CACHE_EVICTION_ENABLED = {enabled}
hs._cache_size_estimate = 0
hs._last_enforcement_time = 0
hs._enforce_cache_size_limit(force=True)
after = sorted(p.name for p in tmp.glob("*.pkl"))
total = sum(p.stat().st_size for p in tmp.glob("*.pkl"))
print("AFTER " + " ".join(after))
print("TOTAL " + str(total))
"""
        )
        return _run_in_subprocess(code, {})

    @staticmethod
    def _names(output: str) -> list:
        for line in output.splitlines():
            if line.startswith("AFTER "):
                return line[len("AFTER "):].split()
        raise AssertionError(f"no AFTER line in output: {output}")

    def test_no_deletion_when_eviction_disabled(self):
        """The regression this test exists for: a 2 MB cache over a 1 MB 'limit'."""
        out = self._run_eviction(limit_bytes=1024 * 1024, enabled=False)
        names = self._names(out)
        self.assertEqual(
            len(names),
            5,
            f"all cache files must survive when eviction is disabled, got {names}",
        )

    def test_oldest_files_evicted_when_over_limit(self):
        out = self._run_eviction(limit_bytes=1024 * 1024, enabled=True)
        names = self._names(out)
        self.assertLess(len(names), 5, "oldest files must be evicted")
        self.assertIn("2025-01-05.pkl", names, "the newest file must be kept")

    def test_newest_file_is_never_evicted(self):
        """Even a single oversized file is kept: it is the freshest work."""
        out = self._run_eviction(limit_bytes=1, enabled=True)
        names = self._names(out)
        self.assertIn("2025-01-05.pkl", names)


class TestCacheWriteTracking(unittest.TestCase):
    """The size estimate must stay in sync with what is on disk."""

    def test_write_helper_tracks_size_delta(self):
        import services.historical_service as hs

        with tempfile.TemporaryDirectory() as tmp:
            cache_file = Path(tmp) / "2025-01-01.pkl"
            original_estimate = hs._cache_size_estimate
            hs._cache_size_estimate = 0
            try:
                hs._write_cache_file(cache_file, {"a": 1})
                self.assertEqual(
                    hs._cache_size_estimate, cache_file.stat().st_size
                )
                # Rewriting the same file must not double count its size.
                hs._write_cache_file(cache_file, {"a": 1, "b": 2})
                self.assertEqual(
                    hs._cache_size_estimate, cache_file.stat().st_size
                )
            finally:
                hs._cache_size_estimate = original_estimate


if __name__ == "__main__":
    unittest.main()
