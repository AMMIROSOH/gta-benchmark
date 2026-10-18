"""Verify fresh, changing snapshots from the real game, including player data."""

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from reader.sa_telemetry import state


def verify(samples, require_simulation=True):
    failures = []
    active = [sample for sample in samples if sample.get("live") and sample.get("player")]
    if len(active) < 3:
        failures.append("Fewer than three fresh player snapshots; load a save or start a new game.")
    if len({sample.get("sample_count") for sample in active}) < 3:
        failures.append("The plugin sample counter did not advance through three snapshots.")
    if require_simulation and len({sample.get("game_time_ms") for sample in active}) < 2:
        failures.append("The game clock did not advance; resume gameplay for verification.")
    for sample in active:
        player = sample["player"]
        numbers = [*player["position"].values(), player["health"], player["armour"],
                   player["max_health"], player["heading_radians"], player["speed_mps"]]
        if not all(math.isfinite(value) for value in numbers):
            failures.append("Non-finite player data received.")
        if not 0 < player["max_health"] <= 2000 or not 0 <= player["wanted_level"] <= 6:
            failures.append("Player values are outside expected vanilla ranges.")
        clock = sample["clock"]
        # The engine clock's seconds field can temporarily exceed 59 before normalization.
        if not 0 <= clock["hour"] < 24 or not 0 <= clock["minute"] < 60:
            failures.append("Invalid game clock hour or minute.")
        if sample["sampling_errors"]:
            failures.append("The plugin reported a sampling exception.")
        if sample["vehicle"] and not 400 <= sample["vehicle"]["model_id"] <= 611:
            failures.append("Unexpected vehicle model ID for the unmodified game.")
    if len({sample["process_id"] for sample in active}) > 1:
        failures.append("Game process changed during verification.")
    return sorted(set(failures))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait", type=float, default=30)
    parser.add_argument("--connection-only", action="store_true",
                        help="Verify fresh player telemetry without requiring unpaused simulation")
    args = parser.parse_args()
    deadline = time.monotonic() + args.wait
    while True:
        first = state()
        if first.get("live") and first.get("player"):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.25)
    samples = [first]
    for _ in range(29):
        time.sleep(0.15)
        samples.append(state())
    failures = verify(samples, require_simulation=not args.connection_only)
    active = [sample for sample in samples if sample.get("live") and sample.get("player")]
    advanced = len({sample["game_time_ms"] for sample in active}) >= 2
    report = {"passed": not failures,
              "verification_mode": "connection_only" if args.connection_only else "gameplay",
              "simulation_advanced": advanced,
              "unique_sample_counters": len({sample["sample_count"] for sample in active}),
              "maximum_sample_age_ms": max((sample["sample_age_ms"] for sample in active), default=None),
              "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "failures": failures, "observations": len(samples),
              "first": samples[0], "last": samples[-1]}
    runtime = ROOT / "runtime"
    runtime.mkdir(exist_ok=True)
    basename = "connection-verification" if args.connection_only else "verification"
    (runtime / f"{basename}.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    with (runtime / f"{basename}-samples.jsonl").open("w", encoding="utf-8") as output:
        for sample in samples:
            output.write(json.dumps(sample) + "\n")
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
