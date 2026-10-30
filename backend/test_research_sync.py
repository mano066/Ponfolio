"""
Tests for the research-library Drive sync endpoints.

    python -m unittest test_research_sync -v

Google Drive is replaced by an in-memory dict, so these run offline and pin
what would lose a report: an upload that does not reach Drive, a removed
report whose file lingers, and a file name that could escape the sync folder.
"""

import asyncio
import base64
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException


class FakeDrive:
    """Just enough of google_auth's Drive surface for the endpoints."""

    def __init__(self):
        self.files = {}  # name -> bytes

    def get_profile(self):
        return {"email": "t@example.com"}

    def drive_get_content(self, name):
        return self.files.get(name)

    def drive_list_files(self, prefix=None):
        return [{"id": n, "name": n} for n in self.files if not prefix or n.startswith(prefix)]

    def drive_upload_file(self, name, data_dir=None):
        self.files[name] = (Path(data_dir) / name).read_bytes()
        return True

    def drive_delete_file(self, file_id):
        return self.files.pop(file_id, None) is not None


class ResearchSyncTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import main
        cls.main = main

    def setUp(self):
        self.drive = FakeDrive()
        self.tmp = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(self.main, "_expense_dir", return_value=Path(self.tmp.name))]
        for fn in ("get_profile", "drive_get_content", "drive_list_files", "drive_upload_file", "drive_delete_file"):
            patches.append(mock.patch.object(self.main.google_auth, fn, getattr(self.drive, fn)))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def run_(self, coro):
        return asyncio.run(coro)

    def test_empty_drive_pulls_an_empty_library(self):
        r = self.run_(self.main.research_drive_pull())
        self.assertEqual(r, {"authenticated": True, "library": {"docs": [], "removed": []}, "files": []})

    def test_push_then_pull_round_trips_index_and_file(self):
        body = b"<h1>report</h1>"
        lib = {"docs": [{"id": "user-1", "title": "R", "drive_file": "research_file_user-1.html"}], "removed": []}
        r = self.run_(self.main.research_drive_push(
            {"library": lib, "files": {"research_file_user-1.html": base64.b64encode(body).decode()}}))
        self.assertTrue(r["ok"])
        pulled = self.run_(self.main.research_drive_pull())
        self.assertEqual(pulled["library"], lib)
        self.assertEqual(pulled["files"], ["research_file_user-1.html"])
        f = self.run_(self.main.research_drive_file(name="research_file_user-1.html"))
        self.assertEqual(base64.b64decode(f["data"]), body)

    def test_removed_report_file_is_deleted_from_drive(self):
        self.drive.files["research_file_user-7.pdf"] = b"%PDF"
        self.drive.files["research_file_user-8.pdf"] = b"%PDF"
        r = self.run_(self.main.research_drive_push({"library": {"docs": [], "removed": ["user-7"]}, "files": {}}))
        self.assertEqual(r["deleted"], ["research_file_user-7.pdf"])
        self.assertIn("research_file_user-8.pdf", self.drive.files)
        self.assertEqual(json.loads(self.drive.files["research_library.json"])["removed"], ["user-7"])

    def test_rejects_names_outside_the_research_pattern(self):
        for bad in ("../main.py", "portfolio.json", "research_file_user-1.exe"):
            with self.assertRaises(HTTPException):
                self.run_(self.main.research_drive_file(name=bad))
            with self.assertRaises(HTTPException):
                self.run_(self.main.research_drive_push({"library": {}, "files": {bad: "eA=="}}))
        self.assertNotIn("portfolio.json", self.drive.files)

    def test_signed_out_pull_says_so_and_push_refuses(self):
        with mock.patch.object(self.main.google_auth, "get_profile", return_value=None):
            self.assertEqual(self.run_(self.main.research_drive_pull()), {"authenticated": False})
            with self.assertRaises(HTTPException):
                self.run_(self.main.research_drive_push({"library": {}, "files": {}}))


if __name__ == "__main__":
    unittest.main()
