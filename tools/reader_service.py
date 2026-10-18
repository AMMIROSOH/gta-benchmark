"""Start, inspect or stop this project's hidden local telemetry reader."""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
RECORD = ROOT / "runtime/reader-service.json"
URL = "http://127.0.0.1:8765/state"
kernel = ct.WinDLL("kernel32", use_last_error=True)
kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
kernel.OpenProcess.restype = wt.HANDLE
kernel.GetProcessTimes.argtypes = [wt.HANDLE, *([ct.POINTER(wt.FILETIME)] * 4)]
kernel.GetProcessTimes.restype = wt.BOOL
kernel.TerminateProcess.argtypes = [wt.HANDLE, wt.UINT]
kernel.TerminateProcess.restype = wt.BOOL
kernel.CloseHandle.argtypes = [wt.HANDLE]
kernel.CloseHandle.restype = wt.BOOL


def process_handle(pid, terminate=False):
    return kernel.OpenProcess(0x1000 | (1 if terminate else 0), False, pid)


def created_at(handle):
    times = [wt.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(handle, *(ct.byref(value) for value in times)):
        raise ct.WinError(ct.get_last_error())
    return (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime


def read_api():
    # Never send local game data through a configured network proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL, timeout=2) as response:
        if not response.headers.get("Server", "").startswith("SAAgentTelemetry/"):
            raise RuntimeError("Port 8765 belongs to a different server.")
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "status", "stop"))
    args = parser.parse_args()
    record = json.loads(RECORD.read_text()) if RECORD.is_file() else None
    if args.action == "status":
        print(json.dumps({"url": URL, "reader": record, "game": read_api()}, indent=2))
        return
    if args.action == "stop":
        if not record:
            print("No reader started by this project is recorded.")
            return
        handle = process_handle(record["pid"], terminate=True)
        try:
            if handle and created_at(handle) == record["created_at"]:
                if not kernel.TerminateProcess(handle, 0):
                    raise ct.WinError(ct.get_last_error())
                print(f"Stopped this project's reader process {record['pid']}.")
            else:
                print("Recorded reader is no longer running; no process was stopped.")
        finally:
            if handle:
                kernel.CloseHandle(handle)
        RECORD.unlink(missing_ok=True)
        return
    try:
        read_api()
    except (urllib.error.URLError, TimeoutError, ConnectionError):
        pass
    else:
        print(f"Reader already available: {URL}")
        return
    (ROOT / "logs").mkdir(exist_ok=True)
    RECORD.parent.mkdir(exist_ok=True)
    with (ROOT / "logs/reader-service.log").open("a", encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable, str(ROOT / "reader/sa_telemetry.py"),
                                    "--serve", "8765"], cwd=ROOT,
                                   stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
    handle = process_handle(process.pid)
    if not handle:
        raise ct.WinError(ct.get_last_error())
    try:
        record = {"pid": process.pid, "created_at": created_at(handle),
                  "url": URL, "python": sys.executable}
    finally:
        kernel.CloseHandle(handle)
    for _ in range(40):
        if process.poll() is not None:
            raise RuntimeError("Reader exited; inspect logs/reader-service.log.")
        try:
            read_api()
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            time.sleep(0.1)
            continue
        RECORD.write_text(json.dumps(record, indent=2), encoding="utf-8")
        print(f"Started hidden reader, PID {process.pid}: {URL}")
        return
    raise RuntimeError("Reader did not become ready; inspect logs/reader-service.log.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, urllib.error.URLError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
