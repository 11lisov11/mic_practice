Update 2026100705, not a complete HV release.
Verify readback after programming. See RESULTS.json for the recorded connected-stand test.
Use nucleo/*.hex through ST-Link and uno_q/*.elf-zsk.bin through the Arduino UNO Q loader.
Keep the mains input physically disconnected and DC-link discharged during programming.
Linux HMI files preserve the original control credential and Vbus calibration.
The main firmware/ready_to_flash package is older; do not use it to overwrite this update.
From the repository: tools/capture_fault_diagnostics.py reads Wi-Fi status/logs without commands.
tools/wifi_motor_first_start.py permits one guarded V/f trial only after operator readiness.
No USB, ST-Link or analyzer wires may remain attached to the energized unisolated stand.
Rotation after the RX fix and qualified Nucleo phase-current telemetry are still unverified.
