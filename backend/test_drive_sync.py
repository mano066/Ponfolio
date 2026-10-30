"""
Tests for Drive sync not piling up a new version on every save.

    python -m unittest test_drive_sync -v

No network: httpx and the auth header are patched. What is under test is the
decision to upload at all — identical bytes must cost nothing on Drive.
"""

import hashlib
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import google_auth


def _resp(status=200, payload=None):
    return types.SimpleNamespace(status_code=status,
                                 json=lambda: payload or {})


class DriveSyncFileTestCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.file = self.dir / "portfolio.json"
        self.file.write_bytes(b'[{"symbol": "ITC"}]')
        self.md5 = hashlib.md5(self.file.read_bytes()).hexdigest()
        patches = [
            mock.patch.object(google_auth, "_drive_headers",
                              return_value={"Authorization": "Bearer x"}),
            mock.patch.object(google_auth, "drive_find_or_create_folder",
                              return_value="folder"),
            mock.patch.object(google_auth, "drive_delete_file", return_value=True),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def _run(self, listed):
        with mock.patch.object(google_auth.httpx, "get",
                               return_value=_resp(200, {"files": listed})), \
             mock.patch.object(google_auth.httpx, "patch",
                               return_value=_resp(200)) as patch, \
             mock.patch.object(google_auth.httpx, "post",
                               return_value=_resp(200)) as post:
            status = google_auth.drive_sync_file("portfolio.json", self.dir)
        return status, patch, post

    def test_identical_bytes_are_not_uploaded(self):
        status, patch, post = self._run(
            [{"id": "f1", "md5Checksum": self.md5}])
        self.assertEqual(status, google_auth.SYNC_UNCHANGED)
        patch.assert_not_called()
        post.assert_not_called()

    def test_changed_bytes_update_the_existing_file(self):
        status, patch, post = self._run(
            [{"id": "f1", "md5Checksum": "different"}])
        self.assertEqual(status, google_auth.SYNC_UPDATED)
        patch.assert_called_once()
        post.assert_not_called()

    def test_a_missing_checksum_still_uploads(self):
        status, patch, _ = self._run([{"id": "f1"}])
        self.assertEqual(status, google_auth.SYNC_UPDATED)
        patch.assert_called_once()

    def test_a_new_file_is_created(self):
        status, patch, post = self._run([])
        self.assertEqual(status, google_auth.SYNC_CREATED)
        post.assert_called_once()
        patch.assert_not_called()

    def test_unchanged_still_counts_as_synced(self):
        with mock.patch.object(google_auth, "drive_sync_file",
                               return_value=google_auth.SYNC_UNCHANGED):
            self.assertTrue(google_auth.drive_upload_file("portfolio.json"))


if __name__ == "__main__":
    unittest.main()
