"""Read and write the game's DB table files by a [name, type] layout (the RPFM schema's fields).

File: optional GUID marker FD FE FC FF + u16 length + UTF-16; version marker FC FD FE FF + i32;
byte 01; u32 row count; rows. Field types as in RPFM: Boolean, I16, I32, I64, F32, F64, ColourRGB,
StringU8, StringU16, OptionalStringU8, OptionalStringU16, OptionalI32.
Floats are read raw (no rounding), so a copied row writes back the same bytes.
"""
import struct
import uuid

GUID_MARKER = b"\xfd\xfe\xfc\xff"
VERSION_MARKER = b"\xfc\xfd\xfe\xff"
_NUM = {"I16": "<h", "I32": "<i", "I64": "<q", "F32": "<f", "F64": "<d", "ColourRGB": "<I"}


def header(b):
    """(guid or None, version or None, offset of the row count)."""
    p, guid, version = 0, None, None
    if b[:4] == GUID_MARKER:
        n = struct.unpack_from("<H", b, 4)[0]
        guid = b[6:6 + 2 * n].decode("utf-16-le")
        p = 6 + 2 * n
    if b[p:p + 4] == VERSION_MARKER:
        version = struct.unpack_from("<i", b, p + 4)[0]
        p += 8
    return guid, version, p + 1


def _read(b, p, t):
    if t in _NUM:
        fmt = _NUM[t]
        return struct.unpack_from(fmt, b, p)[0], p + struct.calcsize(fmt)
    if t == "Boolean":
        if b[p] not in (0, 1):
            raise ValueError(f"flag {b[p]} at {p}")
        return bool(b[p]), p + 1
    if t in ("StringU8", "StringU16"):
        wide = t == "StringU16"
        n = struct.unpack_from("<H", b, p)[0] * (2 if wide else 1)
        raw = b[p + 2:p + 2 + n]
        if len(raw) != n:
            raise ValueError(f"text past the end at {p}")
        return raw.decode("utf-16-le" if wide else "utf-8"), p + 2 + n
    if t.startswith("Optional"):
        present, p = _read(b, p, "Boolean")
        return _read(b, p, t.removeprefix("Optional")) if present else (None, p)
    raise KeyError(t)


def _write(v, t):
    if t in _NUM:
        return struct.pack(_NUM[t], v)
    if t == "Boolean":
        return b"\x01" if v else b"\x00"
    if t == "StringU8":
        raw = v.encode("utf-8")
        return struct.pack("<H", len(raw)) + raw
    if t == "StringU16":
        raw = v.encode("utf-16-le")
        return struct.pack("<H", len(raw) // 2) + raw
    if t.startswith("Optional"):
        return b"\x00" if v is None else b"\x01" + _write(v, t.removeprefix("Optional"))
    raise KeyError(t)


def decode(b, fields):
    """Rows as dicts; raises unless the layout reads the file to its last byte."""
    _, _, p = header(b)
    count = struct.unpack_from("<I", b, p)[0]
    p += 4
    rows = []
    for _ in range(count):
        row = {}
        for name, t in fields:
            row[name], p = _read(b, p, t)
        rows.append(row)
    if p != len(b):
        raise ValueError(f"{len(b) - p} bytes left after {count} rows")
    return rows


def encode(rows, fields, version, table):
    """A table file; the GUID is derived from the content, so equal inputs give equal bytes."""
    names = {n for n, _ in fields}
    body = bytearray()
    for row in rows:
        if set(row) != names:
            raise ValueError(f"{table}: row columns differ from the layout: {set(row) ^ names}")
        for name, t in fields:
            body += _write(row[name], t)
    guid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"tww3_mtb/{table}/{version}/" + body.hex())).encode("utf-16-le")
    out = GUID_MARKER + struct.pack("<H", len(guid) // 2) + guid
    if version:
        out += VERSION_MARKER + struct.pack("<i", version)
    return out + b"\x01" + struct.pack("<I", len(rows)) + bytes(body)
