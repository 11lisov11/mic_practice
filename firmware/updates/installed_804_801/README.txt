Installed firmware snapshot, 2026-10-08
======================================
Uno Q MCU: 2026100804. NUCLEO-G431RB: 2026100801.
Linux HMI sources are copied from the same working tree.
This snapshot includes images, original build manifests and bench reports.
manifest.json records SHA-256 for every payload file. The adjacent ZIP is
the complete snapshot, including ELF/BIN images ignored in normal builds.

Uno Q flash artifact: uno_q/UNOQ_MOTOR.ino.elf-zsk.bin
Nucleo image: nucleo/ACIM-NUCLEOG431RB-IPM15B-VF_OL.hex (or .bin at 0x08000000).
Do not substitute the Uno raw .bin for its loader-compatible flash artifact.
Use the repository's board-specific programming instructions and preserve
device-local credentials and calibration. No credentials are included here.

Evidence and limits
-------------------
27 regression suites passed; timing and deferred-log checks also passed.
Two zero-bus active logic runs passed using temporary Nucleo fixture 899;
production 801 was restored and verified. Reports retain exact test scope.
Carrier/deadtime evidence does not independently validate settled 20 Hz.
The software break test is not qualification of physical PA6/IPM protection.
Observed UART TX-gap maximum fell from 365866 to 215575 us (41.08%);
these are accumulated maxima, not independent statistical samples or a
guaranteed worst-case bound. See reports/RESULT_RU.txt and reports/SUMMARY.json.

hardware_acceptance = false
hv_release_approved = false
This is an installed-state archive, not permission to energize a motor.
Older update archives and ready_to_flash bundles are historical snapshots;
consult firmware/updates/RELEASE_STATUS.json for the current archive.
