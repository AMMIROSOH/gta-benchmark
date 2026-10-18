"""Install Python dependencies and FFmpeg on D:, without running a game or model."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sa_agent.config import default_config_path

DOWNLOAD = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("D:/SA-Agent"))
    parser.add_argument("--skip-ffmpeg", action="store_true")
    parser.add_argument("--config", type=Path, default=default_config_path())
    args = parser.parse_args()
    if sys.platform != "win32":
        raise SystemExit("This runtime requires Windows")
    dependency_root = args.root.resolve()
    if dependency_root.drive.lower() != "d:":
        raise SystemExit("Dependencies must stay on D: for this project")
    cache, temporary = dependency_root / "cache", dependency_root / "tmp"
    cache.mkdir(parents=True, exist_ok=True)
    temporary.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(PIP_CACHE_DIR=str(cache / "pip"), TEMP=str(temporary), TMP=str(temporary))
    environment = dependency_root / "venv"
    python = environment / "Scripts/python.exe"
    if not python.is_file():
        print(f"Creating Python environment at {environment}", flush=True)
        subprocess.run([sys.executable, "-m", "venv", str(environment)], check=True, env=env)
    subprocess.run([str(python), "-m", "pip", "install", "-e", str(ROOT)],
                   check=True, env=env, cwd=ROOT)
    benchmark = args.config
    configured_ffmpeg = (json.loads(benchmark.read_text())["recording"]["ffmpeg"]
                         if benchmark.is_file() else "")
    existing_ffmpeg = configured_ffmpeg if Path(configured_ffmpeg).is_file() else shutil.which("ffmpeg")
    if existing_ffmpeg:
        print(f"Reusing installed FFmpeg: {existing_ffmpeg}", flush=True)
    if not args.skip_ffmpeg and not existing_ffmpeg:
        destination = dependency_root / "dependencies/ffmpeg"
        if not (destination / "bin/ffmpeg.exe").is_file():
            archive = cache / "ffmpeg-release-essentials.zip"
            print("Downloading FFmpeg release essentials to D:", flush=True)
            with urllib.request.urlopen(DOWNLOAD + ".sha256", timeout=30) as response:
                checksum_text = response.read(4096).decode("ascii")
            match = re.search(r"\b[0-9a-fA-F]{64}\b", checksum_text)
            if not match:
                raise RuntimeError("FFmpeg publisher checksum is unavailable")
            partial = archive.with_suffix(".zip.partial")
            with urllib.request.urlopen(DOWNLOAD, timeout=120) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            with partial.open("rb") as downloaded:
                digest = hashlib.file_digest(downloaded, "sha256").hexdigest()
            if digest.lower() != match.group().lower():
                raise RuntimeError("FFmpeg checksum mismatch; archive was not installed")
            partial.replace(archive)
            with zipfile.ZipFile(archive) as package:
                for name in ("ffmpeg.exe", "ffprobe.exe"):
                    entries = [entry for entry in package.infolist()
                               if entry.filename.lower().endswith("/bin/" + name)]
                    if len(entries) != 1:
                        raise RuntimeError(f"Expected one {name} in the FFmpeg archive")
                    target = destination / "bin" / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with package.open(entries[0]) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output)
                for entry in package.infolist():
                    basename = Path(entry.filename).name
                    if not entry.is_dir() and ("license" in basename.lower() or basename.lower().startswith("readme")):
                        target = destination / "licenses" / basename
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with package.open(entry) as source, target.open("wb") as output:
                            shutil.copyfileobj(source, output)
            (destination / "download.json").write_text(json.dumps({
                "url": DOWNLOAD, "archive_sha256": digest,
                "publisher": "Gyan Windows build linked from https://ffmpeg.org/download.html",
                "source": "https://github.com/FFmpeg/FFmpeg"
            }, indent=2), encoding="utf-8")
    print(f"Runtime ready: {python}\nNo ASI build, game launch, recording or Jev request was performed.")


if __name__ == "__main__":
    main()
