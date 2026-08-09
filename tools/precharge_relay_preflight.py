#!/usr/bin/env python3
def main() -> int:
    print(
        "PRECHARGE relay preflight is disabled: K1 is not installed and "
        "Blue Pill PB4 must remain NC/high-impedance"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
