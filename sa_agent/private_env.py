"""Load only the project's TypeSafe key from its Git-ignored private env file."""

import json
import os
from pathlib import Path


def load_typesafe_key():
    if os.environ.get("TYPESAFE_API_KEY"):
        return
    path = Path(__file__).resolve().parents[1] / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        name, separator, value = line.partition("=")
        if separator and name.strip() == "TYPESAFE_API_KEY":
            value = value.strip()
            if value.startswith('"'):
                value = json.loads(value)
            if value:
                os.environ["TYPESAFE_API_KEY"] = value
            return
