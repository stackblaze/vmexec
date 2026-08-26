"""
delta_store.py — VMExec incremental delta file format (NVBD1)

The on-disk magic stays b'NVBD' (NovaBak-era): it is written into every delta
file ever produced, and changing it would make existing incrementals unreadable.

Binary layout:
  magic     4 bytes  b'NVBD'
  version   uint16   1
  num_ext   uint32
  repeat num_ext times:
    offset  uint64
    length  uint32
    data    length bytes
"""

import io
import struct

MAGIC = b"NVBD"
VERSION = 1
VERSION_COMPRESSED = 2
HEADER_FMT = "<4sHI"  # magic, version, num_extents
HEADER_FMT_V2 = "<4sHBI"  # magic, version, flags, num_extents
EXTENT_HDR_FMT = "<QI"  # offset, length
HEADER_SIZE = struct.calcsize(HEADER_FMT)
HEADER_SIZE_V2 = struct.calcsize(HEADER_FMT_V2)
EXTENT_HDR_SIZE = struct.calcsize(EXTENT_HDR_FMT)
FLAG_COMPRESSED = 1


class DeltaFormatError(Exception):
    pass


def write_delta_file(path_or_file, extents, compression_level=0):
    """
    Write delta file from list of (offset, data_bytes) tuples.
    path_or_file may be a filesystem path or a file-like object.
    """
    if isinstance(path_or_file, (str, bytes)):
        with open(path_or_file, "wb") as f:
            _write_delta_stream(f, extents, compression_level)
    else:
        _write_delta_stream(path_or_file, extents, compression_level)


def _write_delta_stream(f, extents, compression_level=0):
    from compression_util import compress_bytes, effective_level
    level = effective_level(compression_level)
    use_compression = level > 0
    version = VERSION_COMPRESSED if use_compression else VERSION
    if use_compression:
        f.write(struct.pack(HEADER_FMT_V2, MAGIC, version, FLAG_COMPRESSED, len(extents)))
    else:
        f.write(struct.pack(HEADER_FMT, MAGIC, version, len(extents)))
    for offset, data in extents:
        if not data:
            continue
        payload = data
        if use_compression:
            payload, _ = compress_bytes(data, level)
        f.write(struct.pack(EXTENT_HDR_FMT, int(offset), len(payload)))
        f.write(payload)


def read_delta_file(path_or_file):
    """Return list of (offset, data_bytes) from a delta file."""
    if isinstance(path_or_file, (str, bytes)):
        with open(path_or_file, "rb") as f:
            return _read_delta_stream(f)
    return _read_delta_stream(path_or_file)


def _read_delta_stream(f):
    magic = f.read(4)
    if magic != MAGIC:
        raise DeltaFormatError(f"Invalid delta magic: {magic!r}")
    ver_bytes = f.read(2)
    if len(ver_bytes) < 2:
        raise DeltaFormatError("Truncated delta header")
    version = struct.unpack("<H", ver_bytes)[0]
    flags = 0
    if version == VERSION_COMPRESSED:
        flag_byte = f.read(1)
        if len(flag_byte) < 1:
            raise DeltaFormatError("Truncated v2 delta header")
        flags = flag_byte[0]
    elif version != VERSION:
        raise DeltaFormatError(f"Unsupported delta version: {version}")

    num_ext_bytes = f.read(4)
    if len(num_ext_bytes) < 4:
        raise DeltaFormatError("Truncated delta header")
    num_ext = struct.unpack("<I", num_ext_bytes)[0]

    from compression_util import decompress_bytes
    compressed = version == VERSION_COMPRESSED and (flags & FLAG_COMPRESSED)

    extents = []
    for _ in range(num_ext):
        hdr = f.read(EXTENT_HDR_SIZE)
        if len(hdr) < EXTENT_HDR_SIZE:
            raise DeltaFormatError("Truncated extent header")
        offset, length = struct.unpack(EXTENT_HDR_FMT, hdr)
        data = f.read(length)
        if len(data) < length:
            raise DeltaFormatError("Truncated extent data")
        if compressed:
            data = decompress_bytes(data)
        extents.append((offset, data))
    return extents


def apply_extents_to_file(f, extents, capacity_bytes=None):
    """Apply delta extents to an open file (must support seek/write)."""
    for offset, data in extents:
        f.seek(offset)
        f.write(data)
    if capacity_bytes is not None:
        f.seek(0, io.SEEK_END)
        end = f.tell()
        if end < capacity_bytes:
            f.seek(capacity_bytes - 1)
            f.write(b"\x00")


def merge_extents(extent_lists):
    """Merge multiple delta extent lists in order (later overwrites earlier at same offset)."""
    merged = {}
    order = []
    for extents in extent_lists:
        for offset, data in extents:
            if offset not in merged:
                order.append(offset)
            merged[offset] = data
    return [(off, merged[off]) for off in sorted(order)]
