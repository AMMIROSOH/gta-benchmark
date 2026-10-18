"""Check TypeSafe connectivity without printing the API key or evaluating a task."""

import argparse
import json
import os
from pathlib import Path
import time
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sa_agent.config import default_config_path, load_config
from sa_agent.private_env import load_typesafe_key
from sa_agent.typesafe_http import request_json, TypeSafeHTTPError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=default_config_path())
    args = parser.parse_args()
    load_typesafe_key()
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key:
        raise SystemExit("TYPESAFE_API_KEY is missing from the environment or .env.local")
    endpoint = "https://api.typesafe.ai/v1/models"
    config = load_config(args.config)
    proxy = config["agent"].get("proxy")
    started = time.monotonic()
    result = {"endpoint": endpoint, "authenticated": False, "proxy": proxy}
    try:
        body = request_json(endpoint, key, 10, proxy=proxy)
        result.update(http_status=200, authenticated=True,
                      models=[model["name"] for model in body["models"]])
    except TypeSafeHTTPError as error:
        result.update(http_status=error.status, error=str(error))
        if error.status == 451:
            result["error"] = "TypeSafe is not available in this region (HTTP 451)"
    except RuntimeError as error:
        result["error"] = str(error)
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    (runtime / "jev-connectivity.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result["authenticated"] else 1)


if __name__ == "__main__":
    main()
