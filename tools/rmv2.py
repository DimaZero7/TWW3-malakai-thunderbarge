"""Reader, editor and writer of the game's rigid_model_v2 files (versions 7 and 8). Standard library only.

File layout, following AssetEditor's Shared/GameFiles/RigidModel and checked by round trip on the game's own files:
header (magic RMV2, version, LOD count, skeleton name 128 bytes), LOD headers (28 bytes each), then each LOD's meshes.
A mesh: a header of 80 bytes (flags, section size, vertex and index offsets and counts, bounding box, shader name), a material
block (fixed part of 860 bytes, bone attachment table, textures, strings), the vertices, the 16-bit triangle indices.

Vertices of type 3 (weighted2) are 32 bytes: position (4 half floats x, y, z, w; the real position is xyz * w), two bone
indices, two bone weights, normal, then UV and tangent data that this module carries unchanged. Type 4 (weighted4) is 36 bytes:
the same with four bone indices and four weights; .bone0 and .weight0 etc. are the first two, the others stay in .rest.

  mesh = load(blob)["lods"][0][0]   # a Mesh: .verts (list of Vertex), .tris, .attachments, .material
  save(model)                       # bytes of a new file; bounding boxes and offsets are computed
"""
import struct

HEADER_SIZE = 140
LOD_HEADER_SIZE = 28
MESH_HEADER_SIZE = 80
MATERIAL_FIXED_SIZE = 860
ATTACHMENT_SIZE = 84
TEXTURE_SIZE = 260
IDENTITY = struct.pack("<12f", 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0)
STRIDE = {3: 32, 4: 36}   # the vertex types this module edits; others raise


class Vertex:
    __slots__ = ("x", "y", "z", "w", "bone0", "bone1", "weight0", "weight1", "rest")

    def __init__(self, raw):
        hx, hy, hz, hw = struct.unpack_from("<4e", raw, 0)
        self.w = hw
        self.x, self.y, self.z = hx * hw, hy * hw, hz * hw
        self.bone0, self.bone1, self.weight0, self.weight1 = raw[8], raw[9], raw[10], raw[11]
        self.rest = bytes(raw[12:])

    def pack(self):
        # W is kept: it gives half floats their precision. A value near zero keeps a plain 1.
        w = self.w if self.w else 1.0
        return (struct.pack("<4e", self.x / w, self.y / w, self.z / w, w)
                + bytes((self.bone0, self.bone1, self.weight0, self.weight1)) + self.rest)

    def rebind(self, bone):
        """All weight on one bone. In type 4 the first bytes of .rest are the four weights and .weight0 and 1 are bone indexes 2 and 3."""
        self.bone0, self.bone1 = bone, 0
        if len(self.rest) == 24:
            self.weight0, self.weight1 = 0, 0
            self.rest = bytes((255, 0, 0, 0)) + self.rest[4:]
        else:
            self.weight0, self.weight1 = 255, 0

    def copy(self):
        v = Vertex.__new__(Vertex)
        for name in Vertex.__slots__:
            setattr(v, name, getattr(self, name))
        return v


class Mesh:
    def __init__(self):
        self.flag = 0
        self.render = 0
        self.head_tail = b""     # bytes of the mesh header after the bounding box (shader name and the rest)
        self.fixed = b""         # material block's fixed part
        self.attachments = []    # [(name, bone index)]
        self.textures = []       # raw 260-byte records
        self.strings = []        # raw records
        self.extra = b""         # what stands between the strings and the vertices
        self.vertex_type = 3
        self.verts = []
        self.tris = []           # [(a, b, c)]

    @property
    def name(self):
        return _cstr(self.fixed[2:34])

    def set_name(self, name):
        raw = name.encode("ascii")[:31]
        self.fixed = self.fixed[:2] + raw + bytes(32 - len(raw)) + self.fixed[34:]

    def copy(self):
        m = Mesh()
        m.__dict__.update(self.__dict__)
        m.attachments = list(self.attachments)
        m.verts = [v.copy() for v in self.verts]
        m.tris = list(self.tris)
        return m


def _cstr(raw):
    end = raw.find(b"\0")
    return (raw if end < 0 else raw[:end]).decode("latin1")


def load(blob):
    if blob[:4] != b"RMV2":
        raise ValueError("not a rigid_model_v2")
    version, lod_count = struct.unpack_from("<II", blob, 4)
    if version not in (7, 8):
        raise ValueError(f"version {version}")
    model = {"version": version, "skeleton": _cstr(blob[12:140]), "lods": [], "lod_headers": []}
    for li in range(lod_count):
        at = HEADER_SIZE + li * LOD_HEADER_SIZE
        mesh_count, _, _, first = struct.unpack_from("<IIII", blob, at)
        model["lod_headers"].append(bytes(blob[at + 16:at + LOD_HEADER_SIZE]))    # distance, level, quality, three bytes
        meshes, off = [], first
        for _ in range(mesh_count):
            flag, render, section, voff, vcount, ioff, icount = struct.unpack_from("<HHIIIII", blob, off)
            mesh = Mesh()
            mesh.flag, mesh.render = flag, render
            mesh.head_tail = bytes(blob[off + 48:off + MESH_HEADER_SIZE])
            mat = off + MESH_HEADER_SIZE
            mesh.vertex_type = struct.unpack_from("<H", blob, mat)[0]
            mesh.fixed = bytes(blob[mat:mat + MATERIAL_FIXED_SIZE])
            nattach, ntex, nstr = struct.unpack_from("<III", blob, mat + 712)
            p = mat + MATERIAL_FIXED_SIZE
            for _ in range(nattach):
                # A record: name of 32 bytes, a 3 x 4 matrix (identity in the game's files), bone index.
                mesh.attachments.append((_cstr(blob[p:p + 32]), struct.unpack_from("<i", blob, p + 80)[0], bytes(blob[p + 32:p + 80])))
                p += ATTACHMENT_SIZE
            for _ in range(ntex):
                mesh.textures.append(bytes(blob[p:p + TEXTURE_SIZE]))
                p += TEXTURE_SIZE
            for _ in range(nstr):
                length = struct.unpack_from("<H", blob, p + 4)[0]
                mesh.strings.append(bytes(blob[p:p + 6 + length]))
                p += 6 + length
            mesh.extra = bytes(blob[p:off + voff])
            stride = (ioff - voff) // vcount if vcount else 0
            if mesh.vertex_type not in STRIDE or stride != STRIDE[mesh.vertex_type]:
                raise ValueError(f"vertex type {mesh.vertex_type}, stride {stride}: not supported")
            at_v = off + voff
            mesh.verts = [Vertex(blob[at_v + i * stride:at_v + (i + 1) * stride]) for i in range(vcount)]
            idx = struct.unpack_from(f"<{icount}H", blob, off + ioff)
            mesh.tris = [idx[i:i + 3] for i in range(0, icount, 3)]
            meshes.append(mesh)
            off += section
        model["lods"].append(meshes)
    return model


def bounding_box(verts):
    if not verts:
        return (0.0,) * 6
    xs, ys, zs = [v.x for v in verts], [v.y for v in verts], [v.z for v in verts]
    return (min(xs), min(ys), min(zs), max(xs), max(ys), max(zs))


def _mesh_bytes(mesh):
    mat = bytearray(mesh.fixed)
    struct.pack_into("<I", mat, 712, len(mesh.attachments))
    for (name, bone, matrix) in mesh.attachments:
        raw = name.encode("ascii")
        mat += raw + bytes(32 - len(raw)) + matrix + struct.pack("<i", bone)
    for t in mesh.textures:
        mat += t
    for s in mesh.strings:
        mat += s
    mat += mesh.extra
    voff = MESH_HEADER_SIZE + len(mat)
    verts = b"".join(v.pack() for v in mesh.verts)
    ioff = voff + len(verts)
    idx = b"".join(struct.pack("<3H", *t) for t in mesh.tris)
    section = ioff + len(idx)
    head = struct.pack("<HHIIIII", mesh.flag, mesh.render, section, voff, len(mesh.verts), ioff, len(mesh.tris) * 3)
    head += struct.pack("<6f", *bounding_box(mesh.verts)) + mesh.head_tail
    if len(head) != MESH_HEADER_SIZE:
        raise ValueError("mesh header size")
    return head + bytes(mat) + verts + idx, len(verts), len(idx)


def save(model):
    lods = len(model["lods"])
    out = bytearray(b"RMV2" + struct.pack("<II", model["version"], lods))
    raw = model["skeleton"].encode("ascii")
    out += raw + bytes(128 - len(raw))
    table_at = len(out)
    out += bytes(lods * LOD_HEADER_SIZE)
    for li, meshes in enumerate(model["lods"]):
        first = len(out)
        vsize = isize = 0
        for mesh in meshes:
            blob, vs, ids = _mesh_bytes(mesh)
            out += blob
            vsize += vs
            isize += ids
        struct.pack_into("<IIII", out, table_at + li * LOD_HEADER_SIZE, len(meshes), vsize, isize, first)
        out[table_at + li * LOD_HEADER_SIZE + 16:table_at + (li + 1) * LOD_HEADER_SIZE] = model["lod_headers"][li]
    return bytes(out)


def keep_triangles(mesh, wanted):
    """A copy of the mesh with only the triangles for which wanted(a, b, c) holds, unused vertices removed."""
    out = mesh.copy()
    remap, verts, tris = {}, [], []
    for tri in mesh.tris:
        if wanted(*tri):
            new = []
            for i in tri:
                if i not in remap:
                    remap[i] = len(verts)
                    verts.append(mesh.verts[i].copy())
                new.append(remap[i])
            tris.append(tuple(new))
    out.verts, out.tris = verts, tris
    return out


def append(mesh, other):
    """Adds another mesh's vertices and triangles to this one (same vertex type and material)."""
    base = len(mesh.verts)
    if base + len(other.verts) > 65535:
        raise ValueError("more vertices than 16-bit indices can hold")
    mesh.verts.extend(v.copy() for v in other.verts)
    mesh.tris.extend((a + base, b + base, c + base) for a, b, c in other.tris)


def wsmodel(geometry, materials_by_lod):
    """Text of a .wsmodel: geometry path and one material per part and LOD. materials_by_lod: {lod: [material of part 0, ...]}."""
    lines = ['<model version="1">', f"  <geometry>{geometry}</geometry>", "  <materials>"]
    for lod, materials in sorted(materials_by_lod.items()):
        for part, material in enumerate(materials):
            lines.append(f'    <material part_index="{part}" lod_index="{lod}">{material}</material>')
    lines += ["  </materials>", "</model>", ""]
    return "\n".join(lines).encode("utf-8")
