"""Local state and bounded control access to the ASI bridge."""

import ctypes as ct
from ctypes import wintypes as wt
import math
import os
import secrets
import time

from reader.sa_telemetry import kernel, state as telemetry_state
from .actions import ACTIONS
from .navigation_state import read_navigation
from .actor_state import read_actors

WORLD_NAME = r"Local\SAAgent.World.v1"
CONTROL_NAME = r"Local\SAAgent.Control.v1"
WORLD_MAGIC, CONTROL_MAGIC = 0x57414153, 0x43414153
VEHICLE_KINDS = {0: "automobile", 1: "monster_truck", 2: "quad", 3: "helicopter",
                 4: "plane", 5: "boat", 6: "train", 7: "fake_helicopter", 8: "fake_plane",
                 9: "motorcycle", 10: "bicycle", 11: "trailer"}


class Vehicle(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [(name, ct.c_int32) for name in ("reference", "model", "vehicle_class")] + [
        ("flags", ct.c_uint32)] + [(name, ct.c_float) for name in
        ("x", "y", "z", "heading", "health", "speed_mps", "distance_m")]


class World(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(name, ct.c_uint32) for name in
        ("magic", "schema", "byte_size", "process_id", "capabilities")] + [
        ("sampled_at_ms", ct.c_uint64), ("player_vehicle_ref", ct.c_int32),
        ("player_vehicle_class", ct.c_int32)] + [(name, ct.c_uint32) for name in
        ("is_driver", "render_width", "render_height", "fps_cap", "last_applied_request",
         "nearby_count", "obstacle_mask")] + [
        ("camera_forward_x", ct.c_float), ("camera_forward_y", ct.c_float),
        ("reserved", ct.c_uint32 * 5), ("vehicles", Vehicle * 16)]


class Command(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(name, ct.c_uint32) for name in
        ("magic", "schema", "byte_size", "owner_pid", "request_id")] + [
        ("issued_at_ms", ct.c_uint64), ("expires_at_ms", ct.c_uint64),
        ("action_id", ct.c_uint32), ("enabled", ct.c_uint32), ("reserved", ct.c_uint32 * 4)]


assert ct.sizeof(World) == 800 and ct.sizeof(Vehicle) == 44 and ct.sizeof(Command) == 64

kernel.CreateMutexW.argtypes = [ct.c_void_p, wt.BOOL, wt.LPCWSTR]
kernel.CreateMutexW.restype = wt.HANDLE
kernel.ReleaseMutex.argtypes = [wt.HANDLE]
kernel.ReleaseMutex.restype = wt.BOOL
kernel.FlushProcessWriteBuffers.argtypes = []
kernel.FlushProcessWriteBuffers.restype = None


class BridgeUnavailable(RuntimeError):
    pass


def _world_snapshot():
    handle = kernel.OpenFileMappingW(4, False, WORLD_NAME)
    if not handle:
        raise BridgeUnavailable("Agent bridge is missing. Rebuild/install the ASI, restart GTA, and load a save.")
    pointer = None
    try:
        pointer = kernel.MapViewOfFile(handle, 4, 0, 0, ct.sizeof(World))
        if not pointer:
            raise ct.WinError(ct.get_last_error())
        for _ in range(50):
            before = ct.c_uint32.from_address(pointer).value
            if before & 1:
                time.sleep(0)
                continue
            value = World.from_buffer_copy(ct.string_at(pointer, ct.sizeof(World)))
            after = ct.c_uint32.from_address(pointer).value
            if before == after == (value.sequence & 0xFFFFFFFF):
                if (value.magic, value.schema, value.byte_size) != (WORLD_MAGIC, 1, ct.sizeof(World)):
                    raise BridgeUnavailable("World mapping has no compatible initialized snapshot yet")
                return value
        raise BridgeUnavailable("World snapshot is being updated; no consistent read available")
    finally:
        if pointer:
            kernel.UnmapViewOfFile(pointer)
        kernel.CloseHandle(handle)


class GameClient:
    def read(self):
        result = telemetry_state()
        if not result.get("connected"):
            raise BridgeUnavailable(result.get("message", "GTA is not connected"))
        world = _world_snapshot()
        if world.process_id != result["process_id"]:
            raise BridgeUnavailable("Telemetry and world data belong to different game processes")
        age = max(0, kernel.GetTickCount64() - world.sampled_at_ms)
        result["world"] = {
            "schema": 1, "sample_age_ms": age,
            "control_ready": bool(world.capabilities & 1),
            "video_mode_hook_ready": bool(world.capabilities & 2),
            "profile_enabled": bool(world.capabilities & 4),
            "render_width": world.render_width, "render_height": world.render_height,
            "fps_cap": world.fps_cap, "last_applied_request": world.last_applied_request,
            "player_state": world.reserved[0],
            "camera_forward_xy": {"x": world.camera_forward_x, "y": world.camera_forward_y},
            "obstacles_within_3m": {"player_forward": bool(world.obstacle_mask & 1),
                                     "player_forward_left": bool(world.obstacle_mask & 2),
                                     "player_forward_right": bool(world.obstacle_mask & 4)},
            "nearby_vehicles": [],
        }
        result["navigation"] = read_navigation(result["process_id"])
        result["actors"] = read_actors(result["process_id"])
        if result["vehicle"] is not None:
            result["vehicle"].update(reference=world.player_vehicle_ref,
                                      vehicle_class=world.player_vehicle_class,
                                      is_driver=bool(world.is_driver))
        player = result.get("player")
        geometry = {g["reference"]: g for g in (result.get("navigation") or {}).get("vehicles", [])}
        for item in list(world.vehicles)[:min(world.nearby_count, 16)]:
            position = {"x": item.x, "y": item.y, "z": item.z}
            vehicle = {"reference": item.reference, "model_id": item.model,
                       "kind": VEHICLE_KINDS.get(item.vehicle_class, "unknown"),
                       "vehicle_class": item.vehicle_class, "is_automobile": item.vehicle_class == 0,
                       "position": position, "heading_radians": item.heading,
                       "health": item.health, "speed_mps": item.speed_mps,
                       "distance_m": item.distance_m, "occupied": bool(item.flags & 1),
                       "is_player_vehicle": bool(item.flags & 4)}
            if player:
                delta = {axis: position[axis] - player["position"][axis] for axis in ("x", "y", "z")}
                vehicle["offset_from_player"] = delta
                # Game heading zero is +Y; positive rotation faces toward -X.
                vehicle["bearing_radians"] = math.atan2(-delta["x"], delta["y"])
                # Approximate driver's door approach point; this is geometry,
                # not a teleport or an automatic navigation action.
                vehicle["approx_driver_door"] = {
                    "x": item.x - math.cos(item.heading) * 1.3,
                    "y": item.y - math.sin(item.heading) * 1.3, "z": item.z}
            actual = geometry.get(item.reference)
            if actual and actual["driver_door_valid"]:
                vehicle["driver_door"] = actual["driver_door"]
                vehicle["driver_door_source"] = "CCarEnterExit.GetPositionToOpenCarDoor.CAR_DOOR_LF"
            result["world"]["nearby_vehicles"].append(vehicle)
        return result


class ControlBridge:
    """Only one runner can own this mapping; each command expires within 750 ms."""

    def __init__(self):
        self.mutex = self.handle = self.pointer = None
        self.request_id = secrets.randbelow(0x3FFFFFFF) + 1

    def __enter__(self):
        self.mutex = kernel.CreateMutexW(None, False, r"Local\SAAgent.ControlLease.v1")
        if not self.mutex:
            raise ct.WinError(ct.get_last_error())
        if kernel.WaitForSingleObject(self.mutex, 0) not in (0, 0x80):
            kernel.CloseHandle(self.mutex)
            self.mutex = None
            raise RuntimeError("Another task runner already owns GTA controls")
        try:
            self.handle = kernel.OpenFileMappingW(6, False, CONTROL_NAME)
            if not self.handle:
                raise BridgeUnavailable("Control mapping unavailable; install the updated ASI")
            self.pointer = kernel.MapViewOfFile(self.handle, 6, 0, 0, ct.sizeof(Command))
            if not self.pointer:
                raise ct.WinError(ct.get_last_error())
            self.release()
            return self
        except BaseException:
            self.close()
            raise

    def send(self, action, duration_ms=200, enabled=True, goal=None):
        if not self.pointer:
            raise RuntimeError("Control bridge is closed")
        if action not in ACTIONS or not 1 <= duration_ms <= 750:
            raise ValueError("Unknown action or invalid input lease duration")
        self.request_id = (self.request_id + 1) & 0xFFFFFFFF or 1
        now = kernel.GetTickCount64()
        command = Command()
        command.magic, command.schema, command.byte_size = CONTROL_MAGIC, 1, ct.sizeof(Command)
        command.owner_pid, command.request_id = os.getpid(), self.request_id
        command.issued_at_ms, command.expires_at_ms = now, now + duration_ms
        command.action_id, command.enabled = ACTIONS[action].code, int(enabled)
        if action.startswith("world_"):
            if not goal or not all(math.isfinite(goal[axis]) and abs(goal[axis]) <= 6000 for axis in ("x", "y")):
                raise ValueError("World movement requires a finite local game-coordinate goal")
            radius = goal.get("stop_radius_m", 0.4)
            if not math.isfinite(radius) or not 0.1 <= radius <= 3:
                raise ValueError("Invalid world-goal stop radius")
            values = (ct.c_float * 4)(goal["x"], goal["y"], radius, 0)
            ct.memmove(ct.addressof(command) + Command.reserved.offset, ct.addressof(values), 16)
        sequence = ct.c_uint32.from_address(self.pointer)
        before = sequence.value
        sequence.value = (before + 1) | 1
        kernel.FlushProcessWriteBuffers()
        ct.memmove(self.pointer + 4, ct.addressof(command) + 4, ct.sizeof(command) - 4)
        kernel.FlushProcessWriteBuffers()
        sequence.value = (sequence.value + 1) & 0xFFFFFFFF
        return self.request_id

    def release(self):
        if self.pointer:
            self.send("idle", 1, enabled=False)

    def close(self):
        if self.pointer:
            self.release()
            kernel.UnmapViewOfFile(self.pointer)
            self.pointer = None
        if self.handle:
            kernel.CloseHandle(self.handle)
            self.handle = None
        if self.mutex:
            kernel.ReleaseMutex(self.mutex)
            kernel.CloseHandle(self.mutex)
            self.mutex = None

    def __exit__(self, *_):
        self.close()
