"""Exception code, address and module of the game's newest crash dump. py -3.14 tools/crash_info.py [file.mdmp]"""
import struct
import sys
from pathlib import Path

CRASH = Path.home() / "AppData" / "Roaming" / "The Creative Assembly" / "Warhammer3" / "crash_report"


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else sorted(CRASH.glob("*.mdmp"), key=lambda p: p.stat().st_mtime)[-1]
    with open(path, "rb") as f:
        head = f.read(32)
        sig, ver, count, rva = struct.unpack_from("<IIII", head)
        f.seek(rva)
        dirs = [struct.unpack("<III", f.read(12)) for _ in range(count)]
        streams = {t: (size, at) for t, size, at in dirs}
        size, at = streams[6]
        f.seek(at)
        thread, _ = struct.unpack("<II", f.read(8))
        code, flags, record, address, nparams, _ = struct.unpack("<IIQQII", f.read(32))
        params = struct.unpack(f"<{min(nparams, 15)}Q", f.read(8 * min(nparams, 15)))
        size, at = streams[4]
        f.seek(at)
        n = struct.unpack("<I", f.read(4))[0]
        modules = []
        for _ in range(n):
            base, msize, _, _, name_rva = struct.unpack("<QIIII", f.read(24))
            f.read(108 - 24)
            modules.append((base, msize, name_rva))
        names = []
        for base, msize, name_rva in modules:
            f.seek(name_rva)
            length = struct.unpack("<I", f.read(4))[0]
            names.append((base, msize, f.read(length).decode("utf-16-le")))
    print(path.name, "code", hex(code), "address", hex(address), "params", [hex(p) for p in params])
    for base, msize, name in names:
        if base <= address < base + msize:
            print("in", name, "rva", hex(address - base))
    print("modules not from Windows:")
    for base, msize, name in names:
        low = name.lower()
        if "windows\\" not in low and "system32" not in low:
            print(" ", name)


if __name__ == "__main__":
    main()
