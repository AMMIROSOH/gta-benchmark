"""Inspect a GTA executable without launching or modifying it."""

import argparse
import hashlib
import json
import struct
from pathlib import Path


def inspect(executable: Path) -> dict:
    data = executable.read_bytes()
    if data[:2] != b"MZ":
        raise ValueError("The executable has no DOS/PE header")
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("The executable has no PE signature")
    machine, sections = struct.unpack_from("<HH", data, pe + 4)
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    optional = pe + 24
    magic = struct.unpack_from("<H", data, optional)[0]
    entry = struct.unpack_from("<I", data, optional + 16)[0]
    base = struct.unpack_from("<I" if magic == 0x10B else "<Q", data,
                              optional + (28 if magic == 0x10B else 24))[0]
    section_table = optional + optional_size
    entries = []
    for index in range(sections):
        offset = section_table + index * 40
        name = data[offset:offset + 8].rstrip(b"\0").decode("ascii", "replace")
        virtual_size, rva, size, raw = struct.unpack_from("<IIII", data, offset + 8)
        entries.append({"name": name, "rva": rva, "virtual_size": virtual_size,
                        "raw_size": size, "raw_offset": raw})

    def bytes_at(address: int, length: int = 16):
        rva = address - base
        for section in entries:
            relative = rva - section["rva"]
            if 0 <= relative and relative + length <= section["raw_size"]:
                raw = section["raw_offset"] + relative
                return data[raw:raw + length].hex(" ")
        return None

    version_bytes = bytes_at(0x401000, 4)
    versions = {"55 8b ec 53": "GTA SA 1.0 US Compact",
                "e9 7b 19 16": "GTA SA 1.0 US HoodLum"}
    return {
        "executable": str(executable.resolve()), "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "machine": hex(machine), "pe_format": hex(magic),
        "image_base": hex(base), "entry_point": hex(base + entry),
        "sdk_version_detection": versions.get(version_bytes, "Unknown; inspect SDK signatures"),
        "sections": entries,
        "sdk_detection_bytes": {hex(address): bytes_at(address) for address in
                                (0x401000, 0x82457C, 0x8245BC, 0x8252FC, 0x82533C)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.executable), indent=2))
