"""Host-only New Game preparation. Jev cannot request resets or skip cutscenes."""

import csv
import ctypes as ct
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from reader.sa_telemetry import kernel, process_alive
from .game import BridgeUnavailable, GameClient
from .windows import GameWindow

STATUS_NAME = r"Local\SAAgent.Lifecycle.v1"
COMMAND_NAME = r"Local\SAAgent.Reset.v1"
STATUS_MAGIC, COMMAND_MAGIC = 0x4C414153, 0x52414153
PHASES = {0: "idle", 1: "loading", 2: "preparing_intro", 3: "ready", 4: "failed", 5: "cancelled"}
ERRORS = {0: None, 1: "reset_owner_lost", 2: "reset_deadline", 3: "native_sampling_fault"}
ROOT = Path(__file__).resolve().parents[1]


class ResetCommand(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(name, ct.c_uint32) for name in
        ("magic", "schema", "byte_size", "owner_pid", "request_id")] + [
        ("issued_at_ms", ct.c_uint64), ("expires_at_ms", ct.c_uint64)] + [
        (name, ct.c_uint32) for name in ("action", "target_pid", "flags", "timeout_ms")] + [
        ("reserved", ct.c_uint32 * 2)]


class LifecycleStatus(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(name, ct.c_uint32) for name in
        ("magic", "schema", "byte_size", "process_id", "capabilities")] + [
        ("sampled_at_ms", ct.c_uint64)] + [(name, ct.c_uint32) for name in
        ("request_id", "owner_pid", "phase", "error", "session_generation")] + [
        ("game_state", ct.c_int32), ("flags", ct.c_uint32), ("cutscenes_skipped", ct.c_uint32),
        ("accepted_at_ms", ct.c_uint64), ("completed_at_ms", ct.c_uint64),
        ("reserved", ct.c_uint32 * 4)]


assert ct.sizeof(ResetCommand) == 64 and ct.sizeof(LifecycleStatus) == 96


def read_status():
    handle = kernel.OpenFileMappingW(4, False, STATUS_NAME)
    if not handle:
        raise BridgeUnavailable("New Game bridge unavailable. Build/install the updated ASI and restart GTA.")
    pointer = None
    try:
        pointer = kernel.MapViewOfFile(handle, 4, 0, 0, ct.sizeof(LifecycleStatus))
        if not pointer:
            raise ct.WinError(ct.get_last_error())
        for _ in range(50):
            before = ct.c_uint32.from_address(pointer).value
            if before & 1:
                time.sleep(0)
                continue
            value = LifecycleStatus.from_buffer_copy(ct.string_at(pointer, ct.sizeof(LifecycleStatus)))
            after = ct.c_uint32.from_address(pointer).value
            if before == after == (value.sequence & 0xFFFFFFFF):
                if (value.magic, value.schema, value.byte_size) != (STATUS_MAGIC, 1, ct.sizeof(value)):
                    raise BridgeUnavailable("New Game bridge has no compatible snapshot")
                if not process_alive(value.process_id) or not value.capabilities & 1:
                    raise BridgeUnavailable("New Game bridge is not available in a live game process")
                return {"process_id": value.process_id,
                    "sample_age_ms": max(0, kernel.GetTickCount64() - value.sampled_at_ms),
                    "request_id": value.request_id, "owner_pid": value.owner_pid,
                    "phase": PHASES.get(value.phase, "unknown"),
                    "error": ERRORS.get(value.error, f"native_error_{value.error}"),
                    "session_generation": value.session_generation, "game_state": value.game_state,
                    "player_controllable": bool(value.flags & 2),
                    "controllable_stable": bool(value.flags & 64),
                    "cutscene_active": bool(value.flags & 4), "menu_active": bool(value.flags & 8),
                    "cutscenes_skipped": value.cutscenes_skipped,
                    "accepted_at_ms": value.accepted_at_ms, "completed_at_ms": value.completed_at_ms}
        raise BridgeUnavailable("New Game status is being updated")
    finally:
        if pointer:
            kernel.UnmapViewOfFile(pointer)
        kernel.CloseHandle(handle)


def ensure_game_running(config):
    """Launch only if absent; never kill/relaunch an existing game to reset it."""
    processes = subprocess.check_output([
        "tasklist", "/FI", "IMAGENAME eq gta_sa.exe", "/FO", "CSV", "/NH"
    ], text=True, errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
    pids = [int(row[1]) for row in csv.reader(io.StringIO(processes))
            if len(row) > 1 and row[0].lower() == "gta_sa.exe"]
    if len(pids) > 1:
        raise RuntimeError("More than one GTA SA process is running")
    launched = False
    if not pids:
        if not config["launch_if_missing"]:
            raise RuntimeError("GTA is closed and reset.launch_if_missing is disabled")
        executable = Path(config["executable"]).resolve()
        if executable.name.lower() != "gta_sa.exe" or not executable.is_file():
            raise RuntimeError("reset.executable must point to the installed gta_sa.exe")
        if config["install_bridge_if_closed"]:
            installation = json.loads((ROOT / "config.local.json").read_text(encoding="utf-8"))
            if (Path(installation["game_dir"]) / "gta_sa.exe").resolve() != executable:
                raise RuntimeError("reset.executable differs from config.local.json; refusing to install in another game")
            print("GTA is closed; installing the built bridge before launch.", flush=True)
            installed = subprocess.run([sys.executable, str(ROOT / "tools/install.py")], cwd=ROOT,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
            if installed.returncode:
                raise RuntimeError("Bridge installation failed: " + installed.stdout[-3000:])
        process = subprocess.Popen([str(executable)], cwd=executable.parent)
        pids = [process.pid]
        launched = True
    deadline = time.monotonic() + (config["launch_timeout_seconds"] if launched else 3)
    last_error = "Waiting for the New Game bridge"
    bridge_seen = False
    next_activate = 0
    while time.monotonic() < deadline:
        if not process_alive(pids[0]):
            raise RuntimeError("GTA exited before its New Game bridge became available")
        try:
            status = read_status()
            if not bridge_seen and not launched:
                # An already running game may still be booting. A compatible
                # mapping proves that the reset extension is loaded, so give
                # the title sequence the configured startup time to finish.
                deadline = time.monotonic() + config["launch_timeout_seconds"]
            bridge_seen = True
            last_error = f"GTA has not reached its main menu or gameplay (game state {status['game_state']})"
            if time.monotonic() >= next_activate:
                try:
                    GameWindow.find(pids[0]).activate()
                except RuntimeError:
                    pass
                next_activate = time.monotonic() + 1
            if (status["process_id"] == pids[0] and status["game_state"] in (7, 9) and
                    status["sample_age_ms"] <= 1000):
                return {"process_id": pids[0], "launched_game": launched,
                    "installed_bridge_before_launch": launched and config["install_bridge_if_closed"]}
        except BridgeUnavailable as error:
            last_error = str(error)
        time.sleep(0.2)
    if not launched and not bridge_seen:
        if config["install_bridge_if_closed"] and config["launch_if_missing"]:
            raise RuntimeError(
                "The running GTA does not expose the New Game reset bridge. "
                "Fully exit GTA to the desktop once, then rerun this same command while GTA is closed. "
                "It will install the built ASI and launch GTA automatically. "
                "Starting New Game from GTA's menu does not reload an ASI plugin.")
        raise RuntimeError(
            "The running GTA does not expose the New Game reset bridge. "
            "Fully exit GTA, install the updated ASI with tools/install.py, and relaunch the game.")
    raise RuntimeError(last_error)


class ResetBridge:
    def __init__(self, pid):
        self.pid = pid
        self.handle = kernel.OpenFileMappingW(6, False, COMMAND_NAME)
        self.pointer = None
        if not self.handle:
            raise BridgeUnavailable("New Game command mapping unavailable; update the ASI")
        self.pointer = kernel.MapViewOfFile(self.handle, 6, 0, 0, ct.sizeof(ResetCommand))
        if not self.pointer:
            kernel.CloseHandle(self.handle)
            self.handle = None
            raise ct.WinError(ct.get_last_error())

    def send(self, action, config, request_id=None):
        value = ResetCommand()
        value.magic, value.schema, value.byte_size = COMMAND_MAGIC, 1, ct.sizeof(value)
        value.owner_pid, value.target_pid = os.getpid(), self.pid
        value.request_id = request_id or secrets.randbelow(0xFFFFFFFE) + 1
        value.issued_at_ms = kernel.GetTickCount64()
        value.expires_at_ms = value.issued_at_ms + 2000
        value.action, value.flags = action, int(config["skip_intro"])
        value.timeout_ms = math.ceil(config["timeout_seconds"] * 1000)
        sequence = ct.c_uint32.from_address(self.pointer)
        sequence.value = (sequence.value + 1) | 1
        kernel.FlushProcessWriteBuffers()
        ct.memmove(self.pointer + 4, ct.addressof(value) + 4, ct.sizeof(value) - 4)
        kernel.FlushProcessWriteBuffers()
        sequence.value = (sequence.value + 1) & 0xFFFFFFFF
        return value.request_id

    def close(self):
        if self.pointer:
            kernel.UnmapViewOfFile(self.pointer)
            self.pointer = None
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None


def fresh_start_failures(state, config):
    """Check the real opening location and BMX; never manufacture a fixture."""
    player = state.get("player")
    if not player or state.get("status") != "playing" or not state.get("live"):
        return ["Waiting for live, unpaused player data"]
    failures = []
    if player["in_vehicle"] or player["health"] <= 0 or player["interior"] != 0:
        failures.append("Waiting for living CJ on foot outdoors")
    if player["wanted_level"]:
        failures.append("New Game must start with zero wanted stars")
    start = config["start_position"]
    pos = player["position"]
    if (math.hypot(pos["x"]-start["x"], pos["y"]-start["y"]) > config["start_radius_m"] or
        abs(pos["z"]-start["z"]) > 8):
        failures.append("Waiting for CJ in the opening alley beside the bicycle")
    if config["require_starting_bicycle"] and not any(
        car["model_id"] == 481 and car["distance_m"] <= config["bicycle_radius_m"]
        for car in state["world"]["nearby_vehicles"]):
        failures.append("Waiting for the starting BMX to stream in nearby")
    return failures


def reset_new_game(config, controls, directory, process_info):
    """Caller owns the control mutex for both preparation and the following task."""
    reset = config["reset"]
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    metadata = {"mode": "new_game", "status": "failed", "started_at_utc":
        datetime.now(timezone.utc).isoformat(), **process_info}
    bridge = None
    accepted = completed = False
    request_id = None
    last_status = None
    waiting = []
    try:
        controls.release()
        initial = read_status()
        pid = process_info["process_id"]
        if initial["process_id"] != pid:
            raise RuntimeError("GTA process changed before reset")
        window = GameWindow.find(pid)
        window.activate()
        bridge = ResetBridge(pid)
        request_id = bridge.send(1, reset)
        metadata.update(request_id=request_id, initial_session_generation=initial["session_generation"])
        deadline = started + reset["timeout_seconds"]
        request_deadline = started + 15
        next_send = 0
        next_finish = 0
        stable_since = None
        client = GameClient()
        with (directory / "reset_events.jsonl").open("w", encoding="utf-8") as events:
            while time.monotonic() < deadline:
                now = time.monotonic()
                if not process_alive(pid):
                    raise RuntimeError("GTA exited during New Game preparation")
                try:
                    status = read_status()
                except BridgeUnavailable:
                    stable_since = None
                    time.sleep(0.2)
                    continue
                if status["process_id"] != pid:
                    raise RuntimeError("GTA process changed during reset")
                last_status = status
                events.write(json.dumps({"elapsed_seconds": now-started, "status": status})+"\n")
                matches = status["owner_pid"] == os.getpid() and status["request_id"] == request_id
                accepted = accepted or matches
                if matches and status["phase"] in ("failed", "cancelled"):
                    raise RuntimeError(status["error"] or f"Reset {status['phase']}")
                if not accepted:
                    if now >= request_deadline:
                        raise RuntimeError("GTA did not acknowledge New Game; keep the game foreground")
                    if now >= next_send:
                        bridge.send(1, reset, request_id)
                        next_send = now + 0.5
                    time.sleep(0.2)
                    continue
                if (matches and (status["phase"] == "ready" or
                        (status["phase"] == "preparing_intro" and status["controllable_stable"])) and
                    status["sample_age_ms"] <= 750 and
                    status["player_controllable"] and
                    status["session_generation"] != initial["session_generation"] and window.foreground()):
                    try:
                        state = client.read()
                        waiting = fresh_start_failures(state, reset)
                        if state["process_id"] != pid or max(state["sample_age_ms"],
                                state["world"]["sample_age_ms"]) > config["game"]["telemetry_max_age_ms"]:
                            waiting.append("Waiting for telemetry from the new session")
                        if not waiting:
                            stable_since = stable_since if stable_since is not None else now
                            if now - stable_since >= reset["settle_seconds"]:
                                if status["phase"] == "ready":
                                    metadata.update(status="ready", session_generation=status["session_generation"],
                                        cutscenes_skipped=status["cutscenes_skipped"], initial_state=state)
                                    completed = True
                                    return metadata, state, window
                                if now >= next_finish:
                                    bridge.send(3, reset, request_id)
                                    next_finish = now + 0.5
                        else:
                            stable_since = None
                    except BridgeUnavailable:
                        stable_since = None
                else:
                    stable_since = None
                time.sleep(0.2)
        raise RuntimeError("New Game preparation timed out" + (": " + "; ".join(waiting) if waiting else ""))
    except BaseException as error:
        metadata["error"] = "cancelled_by_user" if isinstance(error, KeyboardInterrupt) else f"{type(error).__name__}: {error}"
        raise
    finally:
        if bridge:
            try:
                if not completed:
                    # Also expires an unacknowledged request. Loading already
                    # committed by the game cannot be rolled back by cancellation.
                    bridge.send(2, reset, request_id)
            except Exception as error:
                metadata["cancel_error"] = f"{type(error).__name__}: {error}"
            finally:
                bridge.close()
        metadata["elapsed_seconds"] = time.monotonic()-started
        metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        metadata["last_native_status"] = last_status
        (directory / "reset.json").write_text(json.dumps(metadata, indent=2, allow_nan=False), encoding="utf-8")
