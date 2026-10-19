"""Read the optional pointer-free navigation mapping produced on the game thread."""

import ctypes as ct
import math
import time

from reader.sa_telemetry import kernel


class Node(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("reference", ct.c_uint32), ("flags", ct.c_uint32)] + [
        (name, ct.c_float) for name in ("x", "y", "z", "width")] + [("links", ct.c_uint32 * 16)]


class Geometry(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("reference", ct.c_int32), ("flags", ct.c_uint32)] + [
        (name, ct.c_float) for name in ("door_x", "door_y", "door_z", "velocity_x", "velocity_y",
        "right_x", "right_y", "forward_x", "forward_y", "half_width", "front_extent", "rear_extent",
        "front_x", "front_y", "front_z")] + [
        ("door_anchors", ct.c_uint32 * 3), ("front_anchors", ct.c_uint32 * 3)]


class Navigation(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(name, ct.c_uint32) for name in (
        "magic", "schema", "byte_size", "process_id", "capabilities")] + [
        ("sampled_at_ms", ct.c_uint64)] + [(name, ct.c_uint32) for name in (
        "node_count", "vehicle_count", "ray_count", "entering_vehicle")] + [
        ("camera_orientation", ct.c_float), ("reserved", ct.c_uint32 * 3),
        ("nodes", Node * 96), ("vehicles", Geometry * 16), ("rays", ct.c_float * 32)]


assert ct.sizeof(Navigation) == 10112 and ct.sizeof(Geometry) == 92


def read_navigation(process_id):
    handle = kernel.OpenFileMappingW(4, False, r"Local\SAAgent.Navigation.v1")
    if not handle:
        return None
    pointer = None
    try:
        pointer = kernel.MapViewOfFile(handle, 4, 0, 0, ct.sizeof(Navigation))
        if not pointer:
            return None
        for _ in range(20):
            before = ct.c_uint32.from_address(pointer).value
            if before & 1:
                time.sleep(0)
                continue
            value = Navigation.from_buffer_copy(ct.string_at(pointer, ct.sizeof(Navigation)))
            if before != ct.c_uint32.from_address(pointer).value or before != value.sequence & 0xFFFFFFFF:
                continue
            if (value.magic, value.schema, value.byte_size, value.process_id) != (
                    0x4E414153, 1, ct.sizeof(Navigation), process_id):
                return None
            def point(item, prefix=""):
                return {axis: getattr(item, prefix + axis) for axis in ("x", "y", "z")}
            return {
                "schema": 1, "sample_age_ms": max(0, kernel.GetTickCount64()-value.sampled_at_ms),
                "world_goals_ready": bool(value.capabilities & 2),
                "entering_vehicle": bool(value.entering_vehicle), "camera_orientation": value.camera_orientation,
                "nodes": [{"reference": n.reference, "road": bool(n.flags & 1),
                    "visible": bool(n.flags & 2), "position": point(n), "width_m": n.width,
                    "links": [ref for ref in n.links if ref != 0xFFFFFFFF]}
                    for n in list(value.nodes)[:min(value.node_count, 96)]],
                "vehicles": [{"reference": g.reference, "openable": bool(g.flags & 1),
                    "lock_status": (g.flags >> 16) & 255,
                    "door_clear": bool(g.flags & 2), "front_clear": bool(g.flags & 4),
                    "door_busy": bool(g.flags & 8), "driver_door_valid": bool(g.flags & 16),
                    "driver_door": point(g, "door_"), "front_stop": point(g, "front_"),
                    "velocity_xy": {"x": g.velocity_x, "y": g.velocity_y},
                    "right_xy": {"x": g.right_x, "y": g.right_y},
                    "forward_xy": {"x": g.forward_x, "y": g.forward_y},
                    "half_width": g.half_width, "front_extent": g.front_extent, "rear_extent": g.rear_extent,
                    "door_anchors": [r for r in g.door_anchors if r != 0xFFFFFFFF],
                    "front_anchors": [r for r in g.front_anchors if r != 0xFFFFFFFF]}
                    for g in list(value.vehicles)[:min(value.vehicle_count, 16)]],
                "rays": [{"heading_radians": i*math.tau/16, "clearance_m": value.rays[i*2],
                    "ground_delta_m": value.rays[i*2+1]} for i in range(min(value.ray_count, 16))],
            }
        return None
    finally:
        if pointer:
            kernel.UnmapViewOfFile(pointer)
        kernel.CloseHandle(handle)
