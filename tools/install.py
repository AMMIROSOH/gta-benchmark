"""Install our ASI and its benchmark profile; preserve the executable, loader and mods."""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess

from inspect_game import inspect

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    config = json.loads((ROOT / "config.local.json").read_text())
    game = Path(config["game_dir"]).resolve()
    sdk = Path(config["plugin_sdk_dir"]).resolve()
    executable = game / "gta_sa.exe"
    version = inspect(executable)
    if not version["sdk_version_detection"].startswith("GTA SA 1.0 US"):
        raise SystemExit("Unsupported game executable; nothing installed.")
    processes = subprocess.check_output([
        "tasklist", "/FI", "IMAGENAME eq gta_sa.exe", "/FO", "CSV", "/NH"
    ], text=True, errors="replace")
    if any(row and row[0].lower() == "gta_sa.exe" for row in csv.reader(io.StringIO(processes))):
        raise SystemExit("Close GTA SA before updating the ASI. The game was not stopped.")
    source = ROOT / "build/Release/SAAgentTelemetry.asi"
    if not source.is_file():
        raise SystemExit("Build SAAgentTelemetry.asi first.")
    inputs = [ROOT / "CMakeLists.txt", *(ROOT / "src").glob("*.cpp"), *(ROOT / "src").glob("*.h")]
    if source.stat().st_mtime_ns < max(path.stat().st_mtime_ns for path in inputs):
        raise SystemExit("The ASI predates the source changes. Run tools/build.py before installing.")
    profile = ROOT / "configs/SAAgentTelemetry.ini"
    if not profile.is_file():
        raise SystemExit("Generate the benchmark profile before installation.")
    loader = game / "vorbisFile.dll"
    if not loader.is_file() or b"InitializeASI" not in loader.read_bytes():
        raise SystemExit("The expected ASI loader is missing; inspect the loader before installation.")
    preserved = {p.name: sha256(p) for p in (executable, loader, game / "SilentPatchSA.asi") if p.is_file()}
    destination = game / "scripts/SAAgentTelemetry.asi"
    destination.parent.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backups = []
    profile_destination = destination.with_suffix(".ini")
    for incoming, target in ((source, destination), (profile, profile_destination)):
        if target.exists() and sha256(incoming) != sha256(target):
            backup = Path("D:/SA-Agent/backups") / stamp / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
            backups.append(str(backup))
        shutil.copy2(incoming, target)
    for name, before in preserved.items():
        if sha256(game / name) != before:
            raise SystemExit(f"Unexpected change to preserved file: {name}")
    revision = subprocess.check_output(["git", "-C", str(sdk), "rev-parse", "HEAD"], text=True).strip()
    manifest = {
        "installed_at_utc": datetime.now(timezone.utc).isoformat(),
        "game": version, "sdk_path": str(sdk), "sdk_commit": revision,
        "installed_plugin": str(destination), "plugin_sha256": sha256(destination),
        "backups": backups, "installed_profile": str(profile_destination),
        "preserved_files_sha256": preserved,
        "loader": "Reused existing Ultimate ASI Loader (vorbisFile.dll)",
        "toolchain": "Existing Visual Studio 2022 / MSVC 14.36 / Windows SDK 10.0.22000.0; not changed",
    }
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "install-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"installed_plugin": str(destination), "sdk_commit": revision,
                      "game_version": version["sdk_version_detection"],
                      "preserved_files": list(preserved), "backups": backups,
                      "profile": str(profile_destination)}, indent=2))


if __name__ == "__main__":
    main()
