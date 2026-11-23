"""Check the real sketch ELF and reject the old kernel-section mutex layout."""
import argparse
import hashlib
import json
from pathlib import Path
import struct


def check_elf(path):
    data = path.read_bytes()
    if data[:6] != b"\x7fELF\x01\x01":
        raise ValueError("Little-endian ELF32 required")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    if header[1] != 40:
        raise ValueError("ARM ELF required")
    offset, entry_size, count, name_index = header[5], header[10], header[11], header[12]
    if entry_size != 40 or not 0 < count < 4096 or name_index >= count:
        raise ValueError("Unsupported ELF section table")
    headers = [struct.unpack_from("<IIIIIIIIII", data, offset + i * entry_size) for i in range(count)]
    names_header = headers[name_index]
    names = data[names_header[4]:names_header[4] + names_header[5]]

    def string(blob, start):
        end = blob.index(b"\0", start)
        return blob[start:end].decode("ascii")

    section_names = [string(names, h[0]) for h in headers]
    mutex_sections = [n for n in section_names if n.startswith("._k_mutex")]
    symbols = []
    for h in headers:
        if h[1] != 2:
            continue
        if h[9] != 16 or h[6] >= count:
            raise ValueError("Unsupported symbol table")
        sh = headers[h[6]]
        strings = data[sh[4]:sh[4] + sh[5]]
        for pos in range(h[4], h[4] + h[5], 16):
            name, _, size, _, _, section = struct.unpack_from("<IIIBBH", data, pos)
            symbol_name = string(strings, name)
            if symbol_name in ("g_control_mutex", "_ZL15g_control_mutex"):
                symbols.append({"name": symbol_name, "bytes": size,
                                "section": section_names[section] if section < count else None})
    passed = not mutex_sections and len(symbols) == 1 and symbols[0]["section"] == ".bss"
    return {"pass": passed, "sha256": hashlib.sha256(data).hexdigest(),
            "kernel_mutex_sections": mutex_sections, "control_mutex_symbols": symbols}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--elf", type=Path, required=True)
    p.add_argument("--negative-elf", type=Path, required=True)
    p.add_argument("--outdir", type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    out.mkdir(parents=True, exist_ok=False)
    current, negative = check_elf(a.elf), check_elf(a.negative_elf)
    r = {"pass": current["pass"] and not negative["pass"], "current": current,
         "negative": negative, "old_kernel_section_detected": not negative["pass"],
         "hardware_commands": 0, "scope": "compiled ELF storage layout; not live restart qualification"}
    (out / "report.json").write_text(json.dumps(r, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(r, indent=2))
    return 0 if r["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
