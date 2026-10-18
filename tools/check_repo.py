"""Validate source, public configuration, tasks and documentation entirely offline."""

import ast
import json
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sa_agent.config import load_config
from sa_agent.tasks import load_task


def main():
    sources = [path for folder in ("sa_agent", "reader", "tools", "tests")
               for path in (ROOT / folder).rglob("*.py")]
    for path in sources:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    public_json = [ROOT / "config.example.json", ROOT / "configs/benchmark.json",
                   *(ROOT / "schemas").glob("*.json")]
    for path in public_json:
        json.loads(path.read_text(encoding="utf-8"))
    load_config(ROOT / "configs/benchmark.json")
    tasks = [load_task(str(path)) for path in sorted((ROOT / "tasks").glob("*.json"))]
    identifiers = [task["id"] for task in tasks]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("Task IDs must be unique")
    documents = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md")]
    for path in documents:
        for target in re.findall(r"\[[^\]]*\]\(([^\s)]+)\)", path.read_text(encoding="utf-8")):
            if target.startswith(("https://", "http://", "mailto:", "#")):
                continue
            relative = unquote(target.split("#", 1)[0])
            if relative and not (path.parent / relative).exists():
                raise ValueError(f"Broken documentation link in {path.relative_to(ROOT)}: {target}")
    tracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--cached", "-z"],
        text=True, creationflags=0x08000000 if sys.platform == "win32" else 0).split("\0")
    for name in filter(None, tracked):
        parts = Path(name).parts
        if (parts[0] in {"runs", "logs", "runtime", "build", ".venv"} or
            name == "config.local.json" or name.endswith(".local.json") or
            (Path(name).name.startswith(".env") and name != ".env.example") or
            Path(name).suffix.lower() in {".asi", ".exe", ".dll", ".pdb"}):
            raise ValueError(f"Local/private/generated file is tracked: {name}")
    print(f"Offline repository checks passed: {len(sources)} Python files, {len(tasks)} tasks, "
          f"{len(documents)} documents. No game or model connection.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, SyntaxError, KeyError, subprocess.SubprocessError) as error:
        print(f"check-repo: {error}", file=sys.stderr)
        raise SystemExit(1)
