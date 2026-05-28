from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PID_FILE = ROOT / "server.pid"
OUT_LOG = ROOT / "server.out.log"
ERR_LOG = ROOT / "server.err.log"
URL = "http://127.0.0.1:8000/"


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage the local Django development server.")
    parser.add_argument("command", choices=["run", "start", "status", "stop"])
    args = parser.parse_args()

    if args.command == "run":
        return run()
    if args.command == "start":
        return start()
    if args.command == "status":
        return status()
    return stop()


def start() -> int:
    if is_running():
        print(f"Already running at {URL}")
        return 0

    OUT_LOG.parent.mkdir(parents=True, exist_ok=True)
    out = OUT_LOG.open("ab")
    err = ERR_LOG.open("ab")
    command = [
        sys.executable,
        "manage.py",
        "runserver",
        "127.0.0.1:8000",
        "--noreload",
        "--verbosity",
        "0",
    ]
    kwargs = {
        "cwd": ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": out,
        "stderr": err,
        "close_fds": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True

    process = subprocess.Popen(command, **kwargs)
    PID_FILE.write_text(str(process.pid), encoding="utf-8")

    for _ in range(40):
        if is_running():
            print(f"Running at {URL}")
            return 0
        if process.poll() is not None:
            print(f"Server exited early with code {process.returncode}. See {ERR_LOG}.")
            return process.returncode or 1
        time.sleep(0.25)

    print(f"Server process started as PID {process.pid}, but {URL} did not respond yet.")
    return 1


def run() -> int:
    command = [
        sys.executable,
        "manage.py",
        "runserver",
        "127.0.0.1:8000",
        "--noreload",
    ]
    process = subprocess.Popen(command, cwd=ROOT)
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    try:
        return process.wait()
    finally:
        PID_FILE.unlink(missing_ok=True)


def status() -> int:
    if is_running():
        print(f"Running at {URL}")
        return 0
    print("Not running.")
    return 1


def stop() -> int:
    pid = read_pid()
    if pid is None:
        print("No server pid file found.")
        return 0
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], check=False, stdout=subprocess.DEVNULL)
        else:
            os.kill(pid, signal.SIGTERM)
    except OSError:
        pass
    PID_FILE.unlink(missing_ok=True)
    print("Stopped.")
    return 0


def is_running() -> bool:
    try:
        with urllib.request.urlopen(URL, timeout=1.0) as response:
            return 200 <= response.status < 500
    except (OSError, urllib.error.URLError):
        return False


def read_pid() -> int | None:
    try:
        return int(PID_FILE.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
