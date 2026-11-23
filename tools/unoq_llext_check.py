"""Reject TLS relocations unsupported by the pinned UNO Q dynamic loader.

This targeted check does not replace physical boot verification or prove all
possible loader compatibility. Parse ELF structure rather than nm text output.
"""
import argparse
import hashlib
import json
from pathlib import Path

from elftools.elf.elffile import ELFFile
from elftools.elf.relocation import RelocationSection
from elftools.elf.enums import ENUM_RELOC_TYPE_ARM

ARM_NAMES = {v: k for k, v in ENUM_RELOC_TYPE_ARM.items() if isinstance(v, int)}


def inspect(path):
    issues = []
    count = 0
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        if elf['e_machine'] != 'EM_ARM' or elf['e_type'] != 'ET_REL':
            issues.append({'reason': 'Expected ARM relocatable sketch'})
        for section in elf.iter_sections():
            if not isinstance(section, RelocationSection):
                continue
            symbols = elf.get_section(section['sh_link'])
            for relocation in section.iter_relocations():
                count += 1
                name = ARM_NAMES.get(relocation['r_info_type'], str(relocation['r_info_type']))
                symbol = symbols.get_symbol(relocation['r_info_sym']).name
                if 'TLS' in name or symbol in ('z_tls_current', '_ZTH13z_tls_current'):
                    issues.append({'section': section.name, 'offset': relocation['r_offset'],
                                   'type': name, 'symbol': symbol})
    return dict(pass_=not issues, file=str(path.resolve()),
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                relocations=count, issues=issues, hardware_validated=False)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--elf', type=Path, required=True)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    result = inspect(a.elf)
    result['pass'] = result.pop('pass_')
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return 0 if result['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
