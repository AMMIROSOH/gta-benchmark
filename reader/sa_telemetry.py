"""Read SAAgentTelemetry using only Python's standard library on Windows."""

import argparse
import ctypes as ct
from ctypes import wintypes as wt
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import sys
import time

MAPPING_NAME = r"Local\SAAgent.Telemetry.v1"
MAGIC = 0x54414153
SCHEMA = 1


class Snapshot(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [
        ("sequence", ct.c_int32),
        *[(name, ct.c_uint32) for name in
          ("magic", "schema", "byte_size", "process_id", "game_version")],
        ("sampled_at_ms", ct.c_uint64),
        *[(name, ct.c_uint32) for name in
          ("game_time_ms", "flags", "sample_count", "error_count")],
        *[(name, ct.c_float) for name in
          ("x", "y", "z", "heading_radians", "health", "max_health", "armour")],
        ("money", ct.c_int32), ("wanted_level", ct.c_uint32),
        ("vehicle_model", ct.c_int32),
        *[(name, ct.c_float) for name in
          ("vehicle_health", "speed_mps", "velocity_x", "velocity_y", "velocity_z")],
        *[(name, ct.c_uint32) for name in
          ("clock_hour", "clock_minute", "clock_second")],
        *[(name, ct.c_int32) for name in ("weather_old", "weather_new", "weapon_type")],
        *[(name, ct.c_uint32) for name in ("ammo_total", "interior", "sdk_version")],
        ("reserved", ct.c_uint32 * 4),
    ]


assert ct.sizeof(Snapshot) == 160, "Unexpected telemetry ABI size"
assert Snapshot.sampled_at_ms.offset == 24
assert Snapshot.x.offset == 48
assert Snapshot.sdk_version.offset == 140

if sys.platform == "win32":
    kernel = ct.WinDLL("kernel32", use_last_error=True)
    kernel.OpenFileMappingW.argtypes = [wt.DWORD, wt.BOOL, wt.LPCWSTR]
    kernel.OpenFileMappingW.restype = wt.HANDLE
    kernel.MapViewOfFile.argtypes = [wt.HANDLE, wt.DWORD, wt.DWORD, wt.DWORD, ct.c_size_t]
    kernel.MapViewOfFile.restype = ct.c_void_p
    kernel.UnmapViewOfFile.argtypes = [ct.c_void_p]
    kernel.UnmapViewOfFile.restype = wt.BOOL
    kernel.CloseHandle.argtypes = [wt.HANDLE]
    kernel.CloseHandle.restype = wt.BOOL
    kernel.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
    kernel.OpenProcess.restype = wt.HANDLE
    kernel.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
    kernel.WaitForSingleObject.restype = wt.DWORD
    kernel.GetTickCount64.argtypes = []
    kernel.GetTickCount64.restype = ct.c_uint64


def process_alive(pid):
    handle = kernel.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
    if not handle:
        return False
    try:
        return kernel.WaitForSingleObject(handle, 0) == 0x102  # WAIT_TIMEOUT
    finally:
        kernel.CloseHandle(handle)


def read_raw():
    if sys.platform != "win32":
        raise OSError("Live telemetry requires Windows")
    handle = kernel.OpenFileMappingW(0x0004, False, MAPPING_NAME)  # FILE_MAP_READ
    if not handle:
        error = ct.get_last_error()
        if error == 2:
            return None
        raise OSError(error, "Unable to open telemetry mapping")
    address = None
    try:
        address = kernel.MapViewOfFile(handle, 0x0004, 0, 0, ct.sizeof(Snapshot))
        if not address:
            raise ct.WinError(ct.get_last_error())
        for _ in range(100):
            sequence_before = ct.c_uint32.from_address(address).value
            if sequence_before & 1:
                time.sleep(0)
                continue
            data = ct.string_at(address, ct.sizeof(Snapshot))
            sequence_after = ct.c_uint32.from_address(address).value
            value = Snapshot.from_buffer_copy(data)
            if sequence_before == sequence_after == (value.sequence & 0xFFFFFFFF):
                if (value.magic, value.schema, value.byte_size) != (MAGIC, SCHEMA, ct.sizeof(Snapshot)):
                    raise ValueError("Telemetry protocol mismatch or mapping not initialized")
                return value
        raise RuntimeError("Writer busy; could not obtain a consistent snapshot")
    finally:
        if address:
            kernel.UnmapViewOfFile(address)
        kernel.CloseHandle(handle)


def state():
    observed = datetime.now(timezone.utc).isoformat()
    value = read_raw()
    if value is None or not process_alive(value.process_id):
        return {"connected": False, "live": False, "status": "game_not_connected",
                "observed_at_utc": observed,
                "message": "Start GTA SA with SAAgentTelemetry.asi installed, then load a game."}
    age = max(0, kernel.GetTickCount64() - value.sampled_at_ms)
    ready = bool(value.flags & 1)
    in_vehicle = bool(value.flags & 2)
    paused = bool(value.flags & 12)
    valid = not bool(value.flags & (16 | 32))
    live = age <= 2000 and valid and value.sample_count > 0
    status = ("stopping" if value.flags & 32 else
              "sampling_error" if value.flags & 16 else
              "waiting_for_game" if value.sample_count == 0 else
              "stale" if age > 2000 else
              "paused" if paused else "playing" if ready else "no_player")
    result = {
        "connected": True, "live": live, "status": status,
        "observed_at_utc": observed, "process_id": value.process_id,
        "game_version": {1001: "GTA SA 1.0 US Compact", 1002: "GTA SA 1.0 US HoodLum"}.get(
            value.game_version, str(value.game_version)),
        "plugin_sdk_version": value.sdk_version, "schema": value.schema,
        "sample_age_ms": age, "sample_count": value.sample_count,
        "sampling_errors": value.error_count, "game_time_ms": value.game_time_ms,
        "player": None, "vehicle": None,
        "clock": {"hour": value.clock_hour, "minute": value.clock_minute,
                  "second": value.clock_second},
        "weather": {"old_type": value.weather_old, "new_type": value.weather_new},
    }
    if ready and valid:
        result["player"] = {
            "position": {"x": value.x, "y": value.y, "z": value.z},
            "heading_radians": value.heading_radians,
            "heading_degrees": math.degrees(value.heading_radians),
            "health": value.health, "max_health": value.max_health,
            "armour": value.armour, "money": value.money,
            "wanted_level": value.wanted_level, "interior": value.interior,
            "weapon_type": value.weapon_type, "ammo_total": value.ammo_total,
            "in_vehicle": in_vehicle, "speed_mps": value.speed_mps,
            "speed_kmh": value.speed_mps * 3.6,
            "velocity_mps": {"x": value.velocity_x, "y": value.velocity_y,
                             "z": value.velocity_z},
        }
        if in_vehicle:
            result["vehicle"] = {"model_id": value.vehicle_model,
                                 "health": value.vehicle_health,
                                 "speed_mps": value.speed_mps,
                                 "speed_kmh": value.speed_mps * 3.6}
    return result


def serve(port):
    class Handler(BaseHTTPRequestHandler):
        server_version = "SAAgentTelemetry/1"

        def do_GET(self):
            path = self.path.partition("?")[0]
            if path not in ("/", "/state", "/health"):
                self.send_error(404)
                return
            try:
                body = state()
                status = 503 if path == "/health" and not body["live"] else 200
            except (OSError, ValueError, RuntimeError) as error:
                status, body = 503, {"connected": False, "live": False,
                                     "status": "reader_error", "message": str(error)}
            encoded = json.dumps(body, allow_nan=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", port), Handler) as server:
        print(f"SA telemetry: http://127.0.0.1:{port}/state", flush=True)
        server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--once", action="store_true", help="Print one JSON snapshot (default)")
    mode.add_argument("--watch", action="store_true", help="Stream JSON snapshots")
    mode.add_argument("--serve", type=int, metavar="PORT", help="Serve a localhost JSON API")
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--count", type=int, default=0, help="Watch sample limit; 0 means unlimited")
    parser.add_argument("--wait", type=float, default=0, help="Wait up to N seconds for live data")
    parser.add_argument("--require-player", action="store_true")
    parser.add_argument("--output", type=Path, help="Save the latest snapshot as JSON")
    args = parser.parse_args()
    if args.interval <= 0 or args.count < 0 or args.wait < 0:
        parser.error("interval must be positive; count and wait cannot be negative")
    if args.serve is not None:
        if not 1 <= args.serve <= 65535:
            parser.error("port must be between 1 and 65535")
        serve(args.serve)
        return
    deadline = time.monotonic() + args.wait
    while True:
        value = state()
        if value["live"] and (not args.require_player or value["player"] is not None):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.2)
    count = 0
    while True:
        print(json.dumps(value, indent=None if args.watch else 2, allow_nan=False), flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            temporary = args.output.with_suffix(args.output.suffix + ".tmp")
            temporary.write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")
            temporary.replace(args.output)
        count += 1
        if not args.watch or (args.count and count >= args.count):
            break
        time.sleep(args.interval)
        value = state()
    if not value["connected"]:
        raise SystemExit(1)
    if args.require_player and (not value["live"] or value["player"] is None):
        raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Telemetry reader: {error}", file=sys.stderr)
        raise SystemExit(1)
