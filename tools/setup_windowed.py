"""Install the pinned upstream windowed-mode ASI for local game recording."""

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
NAME = "III.VC.SA.WindowedMode"
URL = f"https://github.com/ThirteenAG/{NAME}/releases/download/v2.2/{NAME}.zip"
SHA256 = "68039e974af4d0312281e5802fce8ef385b4291fbfc77a94229542fa57140b2a"


def main():
    game = Path(json.loads((ROOT / "config.local.json").read_text())["game_dir"])
    processes = subprocess.check_output([
        "tasklist", "/FI", "IMAGENAME eq gta_sa.exe", "/FO", "CSV", "/NH"
    ], text=True, errors="replace")
    if any(row and row[0].lower() == "gta_sa.exe" for row in csv.reader(io.StringIO(processes))):
        raise SystemExit("Close GTA before installing the windowed-mode plugin.")
    dependency = Path("D:/SA-Agent/dependencies/windowed-mode")
    dependency.mkdir(parents=True, exist_ok=True)
    archive = dependency / f"{NAME}.zip"
    if not archive.is_file():
        with urllib.request.urlopen(URL, timeout=30) as response:
            archive.write_bytes(response.read(16 * 1024 * 1024))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != SHA256:
        raise SystemExit("Windowed-mode release checksum mismatch; nothing installed.")
    with zipfile.ZipFile(archive) as package:
        binary = dependency / f"{NAME}.asi"
        binary.write_bytes(package.read(binary.name))
        for name in ("README.md", "CHANGELOG.md"):
            (dependency / name).write_bytes(package.read(name))
    scripts = game / "scripts"
    scripts.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    for source in (binary, ROOT / "configs" / f"{NAME}.ini"):
        target = scripts / source.name
        if target.exists() and target.read_bytes() != source.read_bytes():
            backup = Path("D:/SA-Agent/backups") / stamp / target.name
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup)
        shutil.copy2(source, target)
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "windowed-mode-install.json").write_text(json.dumps({
        "installed_at_utc": datetime.now(timezone.utc).isoformat(), "release": "v2.2",
        "url": URL, "archive_sha256": SHA256, "installed_binary": str(scripts / binary.name)
    }, indent=2), encoding="utf-8")
    print(f"Installed {NAME} v2.2. Restart GTA to use the configured window size.")


if __name__ == "__main__":
    main()
