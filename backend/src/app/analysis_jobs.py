import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from collections import Counter
from pathlib import Path

from .config import PROJECT_ROOT

DATA = PROJECT_ROOT / "data"
EXPORT_SCRIPT = PROJECT_ROOT / "backend" / "scripts" / "export_frontend_data.py"
MAX_UPLOAD_BYTES = 4 * 1024 ** 3
CHUNK = 1024 * 1024
NAME_ISSUE = re.compile(r"(?<!\d)(\d{4})(?!\d)")


def identify(path):
    from access_parser import AccessParser

    database = AccessParser(str(path))
    tables = {name.lower(): name for name in database.catalog if not name.startswith("MSys")}
    if "fxm_terra" in tables:
        rows = database.parse_table(tables["pub_current_circ"]) if "pub_current_circ" in tables else {}
        numbers = [n for n in rows.get("circ_no", []) if n]
        return "terrestrial", int(numbers[0]) if numbers else None
    if "notice" in tables and "freq" in tables:
        numbers = Counter(n for n in database.parse_table(tables["notice"]).get("wic_no", []) if n)
        return "space", int(numbers.most_common(1)[0][0]) if numbers else None
    return None, None


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        while chunk := stream.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def processes_holding(path):
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    class UniqueProcess(ctypes.Structure):
        _fields_ = [("pid", wintypes.DWORD), ("started", wintypes.FILETIME)]

    class ProcessInfo(ctypes.Structure):
        _fields_ = [("process", UniqueProcess), ("app", ctypes.c_wchar * 256), ("service", ctypes.c_wchar * 64),
                    ("kind", ctypes.c_int), ("status", wintypes.ULONG), ("session", wintypes.DWORD),
                    ("restartable", wintypes.BOOL)]

    try:
        manager = ctypes.WinDLL("rstrtmgr")
        session, key = wintypes.DWORD(), ctypes.create_unicode_buffer(64)
        if manager.RmStartSession(ctypes.byref(session), 0, key):
            return []
        try:
            files = (ctypes.c_wchar_p * 1)(str(path))
            if manager.RmRegisterResources(session, 1, files, 0, None, 0, None):
                return []
            needed, count, reasons = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD()
            manager.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), None, ctypes.byref(reasons))
            if not needed.value:
                return []
            info = (ProcessInfo * needed.value)()
            count = wintypes.UINT(needed.value)
            if manager.RmGetList(session, ctypes.byref(needed), ctypes.byref(count), info, ctypes.byref(reasons)):
                return []
            return sorted({info[i].app for i in range(count.value) if info[i].app})
        finally:
            manager.RmEndSession(session)
    except OSError:
        return []


def replace_with_retry(source, target, attempts=20, delay=0.5):
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt == attempts - 1:
                holders = processes_holding(target) or processes_holding(source)
                who = f"open in {', '.join(holders)}" if holders else "in use by another program"
                raise ValueError(f"{target.name} could not be replaced: it is {who}. Close it and try again.") from None
            time.sleep(delay)


def canonical_name(kind, issue):
    return f"{'ific' if kind == 'space' else 'brific'}{issue}.mdb"


def receive_upload(stream, length, original_name):
    if length <= 0 or length > MAX_UPLOAD_BYTES:
        raise ValueError("file must be between 1 byte and 4 GB")
    DATA.mkdir(parents=True, exist_ok=True)
    temporary = DATA / f".upload-{uuid.uuid4().hex}.part"
    try:
        remaining = length
        with temporary.open("wb") as target:
            while remaining:
                chunk = stream.read(min(CHUNK, remaining))
                if not chunk:
                    raise ValueError("upload ended early")
                target.write(chunk)
                remaining -= len(chunk)
        try:
            kind, issue = identify(temporary)
        except Exception as error:
            raise ValueError(f"{original_name} is not a readable IFIC database: {error}") from error
        if kind is None:
            raise ValueError(f"{original_name} is neither a space IFIC nor a terrestrial BR IFIC database")
        if issue is None:
            match = NAME_ISSUE.search(original_name or "")
            if not match:
                raise ValueError(f"{original_name}: the issue number is not in the file or its name")
            issue = int(match[1])
        name = canonical_name(kind, issue)
        existing = DATA / name
        unchanged = (existing.is_file() and existing.stat().st_size == length
                     and file_sha256(existing) == file_sha256(temporary))
        if not unchanged:
            replace_with_retry(temporary, existing)
        return {"file": name, "kind": kind, "issue": issue, "originalName": original_name, "bytes": length,
                "unchanged": unchanged}
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


class Jobs:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs = {}
        self._running = None

    def get(self, job_id):
        with self._lock:
            job = self._jobs.get(job_id)
            return json.loads(json.dumps(job)) if job else None

    def start(self, files):
        from .analysis.run_issues import plan

        names = []
        for name in files:
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError("files must be plain file names in data/")
            plan(name)
            if not (DATA / name).is_file():
                raise ValueError(f"{name} is not in data/")
            names.append(name)
        if not names:
            raise ValueError("no files to analyse")
        with self._lock:
            if self._running:
                raise RuntimeError("an analysis is already running")
            job_id = uuid.uuid4().hex[:12]
            ordered = sorted(names, key=lambda n: (plan(n)[0], plan(n)[1]))
            self._jobs[job_id] = {"id": job_id, "status": "running", "started": time.time(), "finished": None,
                                  "files": [{"file": n, "kind": plan(n)[0], "issue": plan(n)[1], "status": "queued",
                                             "counts": None, "error": None} for n in ordered],
                                  "exported": False, "error": None}
            self._running = job_id
        threading.Thread(target=self._work, args=(job_id,), daemon=True).start()
        return self.get(job_id)

    def _update(self, job_id, index=None, **changes):
        with self._lock:
            target = self._jobs[job_id] if index is None else self._jobs[job_id]["files"][index]
            target.update(changes)

    def _work(self, job_id):
        files = self.get(job_id)["files"]
        for index, item in enumerate(files):
            self._update(job_id, index, status="running")
            process = subprocess.run([sys.executable, "-m", "app", "run", item["file"], "--no-export"],
                                     cwd=PROJECT_ROOT / "backend" / "src", capture_output=True, text=True,
                                     encoding="utf-8", errors="replace")
            if process.returncode == 0:
                try:
                    result = json.loads(process.stdout[process.stdout.index("{"):])
                    self._update(job_id, index, status="completed", counts=result.get("counts"))
                except ValueError:
                    self._update(job_id, index, status="completed")
            else:
                lines = [line for line in (process.stderr or process.stdout).strip().splitlines() if line.strip()]
                self._update(job_id, index, status="failed", error=lines[-1] if lines else "analysis failed")
        export = subprocess.run([sys.executable, str(EXPORT_SCRIPT)], cwd=PROJECT_ROOT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
        failed = any(f["status"] == "failed" for f in self.get(job_id)["files"])
        with self._lock:
            job = self._jobs[job_id]
            job["exported"] = export.returncode == 0
            if export.returncode != 0:
                job["error"] = "results could not be loaded into the app"
            job["status"] = "failed" if failed or export.returncode != 0 else "completed"
            job["finished"] = time.time()
            self._running = None
