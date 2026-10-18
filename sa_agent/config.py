"""Configuration loading and validation without game or network access."""

import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def default_config_path(root=ROOT):
    local = root / "configs/benchmark.local.json"
    return local if local.is_file() else root / "configs/benchmark.json"


def load_config(path=None):
    path = Path(path) if path is not None else default_config_path()
    try:
        return validate_config(json.loads(path.read_text(encoding="utf-8")))
    except (KeyError, TypeError, OverflowError) as error:
        raise ValueError(f"{path}: missing setting or incorrect value type ({type(error).__name__})") from None


def validate_config(config):
    def known_fields(value, fields, section):
        if not isinstance(value, dict):
            raise ValueError(f"{section} must be an object")
        if set(value)-fields:
            raise ValueError(f"Unknown fields in {section}: " + ", ".join(sorted(set(value)-fields)))

    def number(value, name, minimum=0, inclusive=False, integer=False):
        if (isinstance(value, bool) or not isinstance(value, (int, float)) or
                not math.isfinite(value) or (integer and type(value) is not int) or
                (value < minimum if inclusive else value <= minimum)):
            raise ValueError(f"Invalid numeric setting: {name}")

    known_fields(config, {"agent", "game", "recording", "reset", "output_dir"}, "config")
    agent, game, video = config["agent"], config["game"], config["recording"]
    known_fields(agent, {"name", "model", "endpoint", "api_key_env", "proxy", "decision_hz",
        "request_timeout_seconds", "max_decision_age_seconds", "max_consecutive_errors",
        "minimum_confidence", "history_size"}, "agent")
    known_fields(game, {"width", "height", "fps_cap", "telemetry_max_age_ms", "connection_grace_seconds",
        "pause_grace_seconds", "action_duration_ms", "startup_countdown_seconds"}, "game")
    known_fields(video, {"fps", "width", "height", "ffmpeg", "encoder", "crf", "preset", "audio",
        "device_index", "output_index", "monitor_origin_xy", "max_backlog_seconds",
        "post_success_seconds"}, "recording")
    from .agents import AGENTS
    if not isinstance(agent["name"], str) or agent["name"] not in AGENTS:
        raise ValueError("agent.name must name a registered adapter")
    if not isinstance(agent["model"], str) or not agent["model"].strip():
        raise ValueError("agent.model must be a nonempty string")
    if not isinstance(agent["api_key_env"], str) or not re.fullmatch(r"[A-Z][A-Z0-9_]*", agent["api_key_env"]):
        raise ValueError("agent.api_key_env must name an uppercase environment variable")
    if video.get("audio", False) is not False:
        raise ValueError("This recorder supports silent video; recording.audio must be false")
    for name in ("request_timeout_seconds", "max_decision_age_seconds"):
        number(agent[name], f"agent.{name}")
    for name in ("max_consecutive_errors", "history_size"):
        number(agent[name], f"agent.{name}", integer=True)
    for name in ("telemetry_max_age_ms", "connection_grace_seconds", "pause_grace_seconds"):
        number(game[name], f"game.{name}")
    number(game["startup_countdown_seconds"], "game.startup_countdown_seconds", inclusive=True)
    number(game["action_duration_ms"], "game.action_duration_ms", integer=True)
    number(video["fps"], "recording.fps", integer=True)
    number(video["max_backlog_seconds"], "recording.max_backlog_seconds")
    for group, settings in (("game", game), ("recording", video)):
        for axis in ("width", "height"):
            number(settings[axis], f"{group}.{axis}", minimum=2, inclusive=True, integer=True)
            if settings[axis] % 2:
                raise ValueError("Game and recording dimensions must be even integers")
    if (video["width"], video["height"]) != (game["width"], game["height"]):
        raise ValueError("Game and recording dimensions must match")
    if agent["decision_hz"] not in (5, 10):
        raise ValueError("decision_hz must be 5 or 10")
    if video["fps"] < 30 or game["fps_cap"] != 30:
        raise ValueError("This benchmark profile requires a 30-FPS game cap and recording FPS >= 30")
    if not 1 <= game["action_duration_ms"] <= 750:
        raise ValueError("action_duration_ms must be between 1 and 750")
    if not 0 <= agent["minimum_confidence"] <= 1:
        raise ValueError("minimum_confidence must be between 0 and 1")
    if not isinstance(config["output_dir"], str) or not config["output_dir"].strip():
        raise ValueError("output_dir must be a path string")
    video.setdefault("post_success_seconds", 15)
    number(video["post_success_seconds"], "recording.post_success_seconds", inclusive=True)
    if video["post_success_seconds"] > 120:
        raise ValueError("post_success_seconds must be finite and between 0 and 120")
    reset = config.setdefault("reset", {"mode": "none"})
    known_fields(reset, {"mode", "executable", "launch_if_missing", "install_bridge_if_closed",
        "launch_timeout_seconds", "timeout_seconds", "skip_intro", "settle_seconds",
        "start_position", "start_radius_m", "require_starting_bicycle", "bicycle_radius_m"}, "reset")
    if reset["mode"] not in ("none", "new_game"):
        raise ValueError("reset.mode must be none or new_game")
    if reset["mode"] == "new_game":
        if not isinstance(reset["executable"], str):
            raise ValueError("reset.executable must be a path string")
        for field in ("launch_if_missing", "install_bridge_if_closed", "skip_intro", "require_starting_bicycle"):
            if not isinstance(reset[field], bool):
                raise ValueError(f"reset.{field} must be true or false")
        for field, minimum, maximum in (("launch_timeout_seconds", 1, 300),
                ("timeout_seconds", 10, 600), ("settle_seconds", 0.2, 30),
                ("start_radius_m", 1, 100), ("bicycle_radius_m", 1, 80)):
            if not math.isfinite(reset[field]) or not minimum <= reset[field] <= maximum:
                raise ValueError(f"reset.{field} must be finite and between {minimum} and {maximum}")
        if not all(math.isfinite(reset["start_position"][axis]) and
                   abs(reset["start_position"][axis]) <= 6000 for axis in ("x", "y", "z")):
            raise ValueError("reset.start_position must contain finite GTA coordinates")
    return config
