"""Unit tests for the resumable cache migration utility.

These tests never touch the network: the R2 adapter functions used by
``migrate_cache_to_r2`` are mocked, and every test operates on a temporary
directory so the real ``historical_cache/`` data is never read or written.
"""

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("R2_ENDPOINT", "https://mock.r2.cloudflarestorage.com")
os.environ.setdefault("R2_ACCESS_KEY_ID", "test_access_key")
os.environ.setdefault("R2_SECRET_ACCESS_KEY", "test_secret_key")

import migrate_cache_to_r2 as migration
from services import cache_keys


class MigrationTestCase(unittest.TestCase):
    """Shared fixture: a temporary cache directory with a few fake cache files."""

    def setUp(self):
        # Safety net: the R2 adapter functions must never reach the network from
        # these tests. Any call that is not explicitly mocked degrades to a miss.
        client_patcher = patch("services.r2_service.get_client", return_value=None)
        client_patcher.start()
        self.addCleanup(client_patcher.stop)

        self.cache_dir = Path(tempfile.mkdtemp(prefix="amanoptions_migrate_test_"))
        self.state_file = self.cache_dir / "migration_state.json"

        self.file_names = ["2025-04-04.pkl", "2025-04-05.pkl", "2025-04-07.pkl"]
        self.contents = {}
        for name in self.file_names:
            payload = f"payload-for-{name}".encode("utf-8")
            self.contents[name] = payload
            (self.cache_dir / name).write_bytes(payload)

    def tearDown(self):
        shutil.rmtree(self.cache_dir, ignore_errors=True)

    def _args(self, *extra):
        return [
            "--cache-dir",
            str(self.cache_dir),
            "--state-file",
            str(self.state_file),
            "--bucket",
            "test-bucket",
            *extra,
        ]


class TestKeyLayout(MigrationTestCase):
    """The object key layout must match what the application reads."""

    def test_object_key_uses_historical_cache_prefix(self):
        key = migration.object_key_for(Path("2025-04-04.pkl"))
        self.assertEqual(key, "historical_cache/2025-04-04.pkl")

    def test_object_key_matches_shared_cache_keys_module(self):
        for day in ("2025-04-04", "2025-12-20"):
            self.assertEqual(
                migration.object_key_for(Path(f"{day}.pkl")),
                cache_keys.r2_object_key(day),
            )

    def test_object_key_matches_application_key_construction(self):
        """The application's inline key must stay identical to the tool's key."""
        from services import historical_service

        day_key = "2025-04-04"
        application_key = (
            f"{historical_service.R2_KEY_PREFIX}/{cache_keys.cache_file_name(day_key)}"
        )
        self.assertEqual(
            migration.object_key_for(Path(f"{day_key}.pkl")), application_key
        )

    def test_custom_prefix_is_respected(self):
        key = migration.object_key_for(Path("2025-04-04.pkl"), key_prefix="custom")
        self.assertEqual(key, "custom/2025-04-04.pkl")


class TestListMode(MigrationTestCase):
    def test_list_reports_local_inventory_without_writing(self):
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ) as mock_list:
            exit_code = migration.main(self._args("--list"))

        self.assertEqual(exit_code, 0)
        mock_list.assert_called_once()
        self.assertEqual(mock_list.call_args[0][1], "historical_cache/")

    def test_list_works_without_credentials(self):
        with patch.object(migration, "get_client", return_value=None):
            exit_code = migration.main(self._args("--list"))

        self.assertEqual(exit_code, 0)


class TestDryRun(MigrationTestCase):
    def test_dry_run_never_uploads(self):
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file") as mock_put:
            exit_code = migration.main(self._args("--dry-run"))

        self.assertEqual(exit_code, 0)
        mock_put.assert_not_called()
        self.assertFalse(self.state_file.exists())

    def test_dry_run_reports_planned_actions(self):
        remote = [
            {"key": "historical_cache/2025-04-04.pkl", "size": len(self.contents["2025-04-04.pkl"]), "etag": ""}
        ]
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "put_file"):
            exit_code = migration.main(self._args("--dry-run"))

        self.assertEqual(exit_code, 0)
        # The remaining two files would be uploaded, the existing one skipped.
        plan = migration.plan_upload(
            migration.build_parser().parse_args(self._args("--dry-run")),
            migration.list_cache_files(self.cache_dir),
            migration.MigrationState(self.state_file, "test-bucket", "historical_cache"),
            "test-bucket",
            {item["key"]: item for item in remote},
        )
        actions = sorted(action for _path, _key, action in plan)
        self.assertEqual(actions, ["skip", "upload", "upload"])


class TestUpload(MigrationTestCase):
    def test_upload_writes_expected_key_and_checksum_metadata(self):
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", return_value=True) as mock_put:
            exit_code = migration.main(self._args("--upload"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_put.call_count, len(self.file_names))
        for call in mock_put.call_args_list:
            bucket, key, local_path = call[0][0], call[0][1], call[0][2]
            self.assertEqual(bucket, "test-bucket")
            self.assertTrue(key.startswith("historical_cache/"))
            self.assertTrue(key.endswith(".pkl"))
            metadata = call[1]["metadata"]
            expected_md5 = hashlib.md5(self.contents[local_path.name]).hexdigest()
            self.assertEqual(metadata["md5"], expected_md5)
            self.assertEqual(metadata["source-name"], local_path.name)

    def test_upload_resumes_and_skips_existing_objects(self):
        remote = [
            {
                "key": "historical_cache/2025-04-04.pkl",
                "size": len(self.contents["2025-04-04.pkl"]),
                "etag": "",
            }
        ]
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "put_file", return_value=True) as mock_put:
            exit_code = migration.main(self._args("--upload"))

        self.assertEqual(exit_code, 0)
        uploaded_keys = sorted(call[0][1] for call in mock_put.call_args_list)
        self.assertEqual(
            uploaded_keys,
            ["historical_cache/2025-04-05.pkl", "historical_cache/2025-04-07.pkl"],
        )

    def test_force_reuploads_existing_objects(self):
        remote = [
            {
                "key": "historical_cache/2025-04-04.pkl",
                "size": len(self.contents["2025-04-04.pkl"]),
                "etag": "",
            }
        ]
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "put_file", return_value=True) as mock_put:
            exit_code = migration.main(self._args("--upload", "--force"))

        self.assertEqual(exit_code, 0)
        self.assertEqual(mock_put.call_count, len(self.file_names))

    def test_size_mismatch_triggers_replace(self):
        remote = [
            {"key": "historical_cache/2025-04-04.pkl", "size": 999, "etag": ""}
        ]
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "put_file", return_value=True) as mock_put:
            exit_code = migration.main(self._args("--upload"))

        self.assertEqual(exit_code, 0)
        uploaded_keys = [call[0][1] for call in mock_put.call_args_list]
        self.assertIn("historical_cache/2025-04-04.pkl", uploaded_keys)

    def test_state_file_records_progress_and_supports_resume(self):
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", return_value=True):
            migration.main(self._args("--upload"))

        self.assertTrue(self.state_file.exists())
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(state["bucket"], "test-bucket")
        self.assertEqual(state["key_prefix"], "historical_cache")
        self.assertEqual(len(state["files"]), len(self.file_names))
        for record in state["files"].values():
            self.assertEqual(record["status"], migration.STATUS_UPLOADED)
            self.assertTrue(record["md5"])

    def test_state_file_is_reused_to_skip_already_uploaded_files(self):
        """A second run with an empty R2 index must not re-upload recorded files."""
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", return_value=True):
            migration.main(self._args("--upload"))

        def fake_head(bucket, key):
            return {"size": len(self.contents[Path(key).name]), "etag": "", "metadata": {}}

        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "head_object", side_effect=fake_head), patch.object(
            migration, "put_file", return_value=True
        ) as mock_put:
            exit_code = migration.main(self._args("--upload"))

        self.assertEqual(exit_code, 0)
        mock_put.assert_not_called()


class TestRetry(MigrationTestCase):
    def test_transient_failure_is_retried(self):
        calls = {"count": 0}

        def flaky(*args, **kwargs):
            calls["count"] += 1
            # Fail the first two attempts, then succeed.
            return calls["count"] > 2

        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", side_effect=flaky), patch.object(
            migration.time, "sleep"
        ):
            exit_code = migration.main(self._args("--upload", "--retries", "3"))

        self.assertEqual(exit_code, 0)
        # Two failed attempts plus one successful attempt for the first file, then a
        # single successful attempt for each of the remaining two files.
        self.assertEqual(calls["count"], 5)
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        for record in state["files"].values():
            self.assertEqual(record["status"], migration.STATUS_UPLOADED)

    def test_exhausted_retries_are_reported_as_failure(self):
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", return_value=False), patch.object(
            migration.time, "sleep"
        ):
            exit_code = migration.main(self._args("--upload", "--retries", "1"))

        self.assertEqual(exit_code, 1)
        state = json.loads(self.state_file.read_text(encoding="utf-8"))
        for record in state["files"].values():
            self.assertEqual(record["status"], migration.STATUS_FAILED)


class TestVerify(MigrationTestCase):
    def _remote_objects(self, with_checksums=True):
        objects = []
        for name in self.file_names:
            key = f"historical_cache/{name}"
            entry = {
                "key": key,
                "size": len(self.contents[name]),
                "etag": hashlib.md5(self.contents[name]).hexdigest(),
            }
            objects.append(entry)
        return objects

    def test_verify_passes_when_r2_matches_local(self):
        def fake_head(bucket, key):
            name = Path(key).name
            return {
                "size": len(self.contents[name]),
                "etag": hashlib.md5(self.contents[name]).hexdigest(),
                "metadata": {"md5": hashlib.md5(self.contents[name]).hexdigest()},
            }

        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=self._remote_objects()
        ), patch.object(migration, "head_object", side_effect=fake_head):
            exit_code = migration.main(self._args("--verify"))

        self.assertEqual(exit_code, 0)

    def test_verify_detects_missing_object(self):
        remote = self._remote_objects()[:-1]
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "head_object", return_value=None):
            exit_code = migration.main(self._args("--verify", "--no-checksum"))

        self.assertEqual(exit_code, 1)

    def test_verify_detects_checksum_mismatch(self):
        def fake_head(bucket, key):
            name = Path(key).name
            return {
                "size": len(self.contents[name]),
                "etag": "0" * 32,
                "metadata": {"md5": "0" * 32},
            }

        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=self._remote_objects()
        ), patch.object(migration, "head_object", side_effect=fake_head):
            exit_code = migration.main(self._args("--verify"))

        self.assertEqual(exit_code, 1)

    def test_verify_detects_byte_count_mismatch(self):
        remote = self._remote_objects()
        remote[0] = dict(remote[0], size=remote[0]["size"] + 10)
        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=remote
        ), patch.object(migration, "head_object", return_value=None):
            exit_code = migration.main(self._args("--verify", "--no-checksum"))

        self.assertEqual(exit_code, 1)


class TestOriginalsAreNeverTouched(MigrationTestCase):
    def test_local_files_are_untouched_after_upload(self):
        before = {name: (self.cache_dir / name).read_bytes() for name in self.file_names}

        with patch.object(migration, "get_client", return_value=MagicMock()), patch.object(
            migration, "list_objects", return_value=[]
        ), patch.object(migration, "put_file", return_value=True):
            exit_code = migration.main(self._args("--upload"))

        self.assertEqual(exit_code, 0)
        for name, payload in before.items():
            path = self.cache_dir / name
            self.assertTrue(path.exists(), f"{name} was removed")
            self.assertEqual(path.read_bytes(), payload)

    def test_tool_contains_no_delete_operations(self):
        source = Path(migration.__file__).read_text(encoding="utf-8")
        for dangerous in (
            "delete_object",
            "delete_objects",
            "delete_bucket",
            "shutil.rmtree",
            "os.remove",
            "os.unlink",
            ".unlink(",
        ):
            self.assertNotIn(dangerous, source)


if __name__ == "__main__":
    unittest.main()
