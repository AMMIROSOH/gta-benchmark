"""Reproducibility metadata; no game control, network calls or secret values."""

import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess

from . import __version__
from .config import ROOT


def fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path):
    path = Path(path)
    try:
        if not path.is_file():
            return None
        with path.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()
    except OSError:
        # An optional provenance hash must not prevent an otherwise valid run.
        return None


def source_revision(root=ROOT):
    def git(*args):
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True,
            text=True, timeout=5, creationflags=0x08000000 if os.name == "nt" else 0)
        return result.stdout.strip() if result.returncode == 0 else None
    try:
        commit, status = git("rev-parse", "HEAD"), git("status", "--porcelain")
        return {"commit": commit, "dirty": bool(status) if status is not None else None}
    except (OSError, subprocess.TimeoutExpired):
        return {"commit": None, "dirty": None}


def make_manifest(task, config, policy_mode):
    packages = {}
    for name in ("numpy", "dxcam", "comtypes"):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = None
    executable = Path(config.get("reset", {}).get("executable", ""))
    installed_asi = executable.parent / "scripts/SAAgentTelemetry.asi"
    return {
        "schema_version": 1, "benchmark": "GTA Benchmark", "benchmark_version": __version__,
        "environment": "gta_sa_1_0_us", "source": source_revision(),
        "task": {"id": task["id"], "version": task["version"],
            "sha256": fingerprint({k: v for k, v in task.items() if k != "source_file"})},
        "config_sha256": fingerprint(config), "policy_mode": policy_mode,
        "controller_version": "car_acquisition_v3" if policy_mode == "target_selection_with_road_controller" else None,
        "agent_adapter": config["agent"]["name"], "requested_model": config["agent"]["model"],
        "python": platform.python_version(), "platform": platform.system(),
        "machine": platform.machine(), "packages": packages,
        "game_executable_sha256": file_hash(executable),
        "installed_asi_sha256": file_hash(installed_asi),
        "scenario_deterministic": False,
    }
