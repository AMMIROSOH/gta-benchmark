"""Pointer-free engine actors, inventory, pickups and attributed death events."""
import ctypes as ct
import time
from reader.sa_telemetry import kernel


class Ped(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [(n, ct.c_int32) for n in ("reference", "model", "state")] + [
        ("flags", ct.c_uint32)] + [(n, ct.c_float) for n in ("x", "y", "z", "health", "armour", "heading")]


class Pickup(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("reference", ct.c_uint32), ("model", ct.c_int32), ("type", ct.c_uint32),
                ("amount", ct.c_uint32)] + [(n, ct.c_float) for n in ("x", "y", "z")]


class Kill(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("event_id", ct.c_uint32), ("victim_reference", ct.c_int32), ("weapon", ct.c_int32),
                ("flags", ct.c_uint32), ("occurred_at_ms", ct.c_uint64)] + [(n, ct.c_float) for n in ("x", "y", "z")]


class Weapon(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("type", ct.c_int32), ("ammo", ct.c_uint32), ("slot", ct.c_uint32)]


class Actors(ct.LittleEndianStructure):
    _pack_ = 4
    _fields_ = [("sequence", ct.c_int32)] + [(n, ct.c_uint32) for n in
        ("magic", "schema", "byte_size", "process_id", "capabilities")] + [
        ("sampled_at_ms", ct.c_uint64)] + [(n, ct.c_uint32) for n in
        ("latest_event_id", "ped_count", "pickup_count", "event_count", "selected_slot", "reserved")] + [
        ("peds", Ped*32), ("pickups", Pickup*32), ("events", Kill*128), ("weapons", Weapon*13)]


assert ct.sizeof(Actors) == 6996 and ct.sizeof(Kill) == 36


def read_actors(process_id):
    handle = kernel.OpenFileMappingW(4, False, r"Local\SAAgent.Actors.v1")
    if not handle:
        return None
    pointer = None
    try:
        pointer = kernel.MapViewOfFile(handle, 4, 0, 0, ct.sizeof(Actors))
        if not pointer:
            return None
        for _ in range(20):
            before = ct.c_uint32.from_address(pointer).value
            if before & 1:
                time.sleep(0)
                continue
            value = Actors.from_buffer_copy(ct.string_at(pointer, ct.sizeof(Actors)))
            if before != ct.c_uint32.from_address(pointer).value or before != value.sequence & 0xFFFFFFFF:
                continue
            if (value.magic, value.schema, value.byte_size, value.process_id) != (0x50414153, 1, ct.sizeof(Actors), process_id):
                return None
            point = lambda item: {axis: getattr(item, axis) for axis in ("x", "y", "z")}
            return {"schema": 1, "sampled_at_ms": value.sampled_at_ms,
                "sample_age_ms": max(0, kernel.GetTickCount64()-value.sampled_at_ms),
                "kill_events_ready": bool(value.capabilities & 1), "combat_ready": bool(value.capabilities & 2),
                "latest_event_id": value.latest_event_id, "selected_weapon_slot": value.selected_slot,
                "nearby_peds": [{"reference": p.reference, "model_id": p.model, "state": p.state,
                    "visible": bool(p.flags & 2) if value.capabilities & 4 else None,
                    "ped_type": (p.flags >> 8) & 255 if value.capabilities & 4 else None,
                    "weapon_type": (p.flags >> 16) & 255 if value.capabilities & 4 else None,
                    "in_vehicle": bool(p.flags & 1), "position": point(p), "health": p.health,
                    "armour": p.armour, "heading_radians": p.heading}
                    for p in list(value.peds)[:min(value.ped_count, 32)]],
                "nearby_pickups": [{"reference": p.reference, "model_id": p.model, "type": p.type,
                    "amount": p.amount, "position": point(p)}
                    for p in list(value.pickups)[:min(value.pickup_count, 32)]],
                "kill_events": [{"event_id": e.event_id, "victim_reference": e.victim_reference,
                    "weapon_type": e.weapon, "player_attributed": bool(e.flags & 3),
                    "source": "player_ped" if e.flags & 1 else "player_vehicle",
                    "headshot": bool(e.flags & 4), "occurred_at_ms": e.occurred_at_ms, "position": point(e)}
                    for e in list(value.events)[:min(value.event_count, 128)]],
                "weapons": [{"slot": w.slot, "type": w.type, "ammo_total": w.ammo} for w in value.weapons]}
        return None
    finally:
        if pointer:
            kernel.UnmapViewOfFile(pointer)
        kernel.CloseHandle(handle)
