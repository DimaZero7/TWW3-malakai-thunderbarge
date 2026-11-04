"""Reader of the game's .anim files (version 8) and forward kinematics. numpy only.

Layout, worked out from humanoid03 and checked to the byte: u32 version, u32 1, f32 fps, string16 skeleton, u32 0, f32 seconds, u32 bones,
then per bone string16 name and i32 parent; u32 6, u32 1; bones x i8 translation kind; bones x i8 rotation kind; u32 x 2 range counts (0 or bones),
then per bone range and minimum of translation (3 + 3 floats), per bone range and minimum of rotation (4 + 4 floats); u32 x 2 static counts,
the static values; u32 x 2 dynamic counts, u32 frames, the frames: translations, then rotations, in bone order.
A kind is the bytes of the value, negative when it is stored once as a static one, 0 when the skeleton's own value holds:
12 three floats, 3 three u8 scaled by the range; 8 quaternion of i16, 4 quaternion of u8 scaled by the range.
"""
import struct

import numpy as np


def qmat(q):
    x, y, z, w = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
                     [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
                     [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]], np.float32)


class Anim:
    def __init__(self, blob):
        b = blob
        self.version, _, self.fps = struct.unpack_from("<IIf", b, 0)
        if self.version != 8:
            raise ValueError(f"anim version {self.version}")
        p = 12
        n = struct.unpack_from("<H", b, p)[0]
        self.skeleton = b[p + 2:p + 2 + n].decode()
        p += 2 + n + 4
        self.seconds = struct.unpack_from("<f", b, p)[0]
        p += 4
        count = struct.unpack_from("<I", b, p)[0]
        p += 4
        self.names, self.parents = [], []
        for _ in range(count):
            n = struct.unpack_from("<H", b, p)[0]
            self.names.append(b[p + 2:p + 2 + n].decode())
            self.parents.append(struct.unpack_from("<i", b, p + 2 + n)[0])
            p += 2 + n + 4
        p += 8
        self.t_kind = np.frombuffer(b, np.int8, count, p).copy()
        self.r_kind = np.frombuffer(b, np.int8, count, p + count).copy()
        p += 2 * count
        nt, nr = struct.unpack_from("<II", b, p)
        p += 8
        self.t_range = np.frombuffer(b, "<f4", nt * 6, p).reshape(nt, 6).copy() if nt else None
        p += nt * 24
        self.r_range = np.frombuffer(b, "<f4", nr * 8, p).reshape(nr, 8).copy() if nr else None
        p += nr * 32
        st, sr = struct.unpack_from("<II", b, p)
        p += 8
        self.static_t, self.static_r = {}, {}
        for i in np.nonzero(self.t_kind < 0)[0]:
            size = -int(self.t_kind[i])
            self.static_t[int(i)] = self._t(b, p, size, int(i))
            p += size
        for i in np.nonzero(self.r_kind < 0)[0]:
            size = -int(self.r_kind[i])
            self.static_r[int(i)] = self._r(b, p, size, int(i))
            p += size
        dt, dr, self.frames = struct.unpack_from("<III", b, p)
        p += 12
        self.data_at, self.blob = p, b
        self.frame_size = sum(int(k) for k in self.t_kind if k > 0) + sum(int(k) for k in self.r_kind if k > 0)
        if p + self.frames * self.frame_size > len(b):     # long animations go on in further blocks of up to 64 frames; the first is enough for a pose
            raise ValueError("anim: size does not add up")

    def _t(self, b, p, size, i):
        if size == 12:
            return np.array(struct.unpack_from("<3f", b, p), np.float32)
        raw = np.frombuffer(b, np.uint8, 3, p).astype(np.float32)
        rng = self.t_range[i]
        return rng[3:6] + raw / 255 * rng[:3]

    def _r(self, b, p, size, i):
        if size == 8:
            q = np.frombuffer(b, "<i2", 4, p).astype(np.float32) / 32767
        else:
            raw = np.frombuffer(b, np.uint8, 4, p).astype(np.float32)
            rng = self.r_range[i]
            q = rng[4:8] + raw / 255 * rng[:4]
        return q / (np.linalg.norm(q) + 1e-9)

    def local(self, frame, rest=None):
        """{bone: (translation, quaternion)} of one frame; bones without data take the rest skeleton's."""
        frame = min(frame, self.frames - 1)
        p = self.data_at + frame * self.frame_size
        out_t, out_r = {}, {}
        for i, k in enumerate(self.t_kind):
            if k > 0:
                out_t[i] = self._t(self.blob, p, int(k), i)
                p += int(k)
            elif k < 0:
                out_t[i] = self.static_t[i]
            elif rest is not None:
                out_t[i] = rest[0][i]
            else:
                out_t[i] = np.zeros(3, np.float32)
        for i, k in enumerate(self.r_kind):
            if k > 0:
                out_r[i] = self._r(self.blob, p, int(k), i)
                p += int(k)
            elif k < 0:
                out_r[i] = self.static_r[i]
            elif rest is not None:
                out_r[i] = rest[1][i]
            else:
                out_r[i] = np.array([0, 0, 0, 1], np.float32)
        return out_t, out_r

    def world(self, frame=0, rest=None):
        """4 x 4 matrix of each bone in the model's space, column vectors."""
        t, r = self.local(frame, rest)
        mats = []
        for i, parent in enumerate(self.parents):
            m = np.eye(4, dtype=np.float32)
            m[:3, :3] = qmat(r[i])
            m[:3, 3] = t[i]
            mats.append(mats[parent] @ m if parent >= 0 else m)
        return mats
