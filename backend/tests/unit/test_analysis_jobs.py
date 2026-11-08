import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import requests

from app import analysis_jobs
from app.web_api import make_handler


class UploadAndJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.data = root / "data"
        self.data.mkdir()
        assessment = root / "assessment.json"
        assessment.write_text(json.dumps({"issues": [], "notices": [], "trends": []}), encoding="utf-8")
        self.patch = mock.patch.object(analysis_jobs, "DATA", self.data)
        self.patch.start()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(assessment))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/api"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.patch.stop()
        self.temporary.cleanup()

    def upload(self, name, body=b"database bytes"):
        return requests.post(f"{self.base}/uploads", params={"name": name}, data=body,
                             headers={"Content-Type": "application/octet-stream"}, timeout=10)

    def test_unreadable_file_is_rejected_and_not_kept(self):
        response = self.upload("notes.mdb", b"not an access database")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_file_is_stored_under_the_name_its_contents_give(self):
        with mock.patch.object(analysis_jobs, "identify", return_value=("terrestrial", 3077)):
            response = self.upload("whatever.mdb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["file"], "brific3077.mdb")
        self.assertTrue((self.data / "brific3077.mdb").is_file())

    def test_issue_number_falls_back_to_the_file_name(self):
        with mock.patch.object(analysis_jobs, "identify", return_value=("space", None)):
            response = self.upload("IFIC_3088_extract.mdb")
        self.assertEqual(response.json()["file"], "ific3088.mdb")

    def test_briefly_locked_target_is_retried(self):
        real_replace = analysis_jobs.os.replace
        calls = []

        def flaky(source, target):
            calls.append(target)
            if len(calls) < 3:
                raise PermissionError("locked")
            real_replace(source, target)

        with mock.patch.object(analysis_jobs, "identify", return_value=("space", 3075)), \
                mock.patch.object(analysis_jobs.os, "replace", side_effect=flaky), \
                mock.patch.object(analysis_jobs.time, "sleep"):
            response = self.upload("ific3075.mdb")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(calls), 3)
        self.assertEqual([p.name for p in self.data.iterdir()], ["ific3075.mdb"])

    def test_locked_target_gives_a_clear_error_and_leaves_no_temporary_file(self):
        with mock.patch.object(analysis_jobs, "identify", return_value=("space", 3075)), \
                mock.patch.object(analysis_jobs.os, "replace", side_effect=PermissionError("locked")), \
                mock.patch.object(analysis_jobs.time, "sleep"):
            response = self.upload("ific3075.mdb")
        self.assertEqual(response.status_code, 400)
        self.assertIn("could not be replaced", response.json()["error"])
        self.assertEqual(list(self.data.iterdir()), [])

    def test_identical_upload_keeps_the_existing_file(self):
        (self.data / "ific3075.mdb").write_bytes(b"database bytes")
        with mock.patch.object(analysis_jobs, "identify", return_value=("space", 3075)),                 mock.patch.object(analysis_jobs.os, "replace", side_effect=PermissionError("open in browser")):
            response = self.upload("ific3075.mdb", b"database bytes")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["unchanged"])
        self.assertEqual([p.name for p in self.data.iterdir()], ["ific3075.mdb"])

    def test_analysis_rejects_unknown_names_and_missing_jobs(self):
        response = requests.post(f"{self.base}/analyses", json={"files": ["notes.txt"]}, timeout=5)
        self.assertEqual(response.status_code, 400)
        response = requests.get(f"{self.base}/analyses/doesnotexist", timeout=5)
        self.assertEqual(response.status_code, 404)

    def test_only_one_analysis_runs_at_a_time(self):
        (self.data / "ific3075.mdb").write_bytes(b"x")
        jobs = analysis_jobs.Jobs()
        jobs._running = "busy"
        with self.assertRaises(RuntimeError):
            jobs.start(["ific3075.mdb"])


if __name__ == "__main__":
    unittest.main()
