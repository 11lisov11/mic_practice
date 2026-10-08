# External SD/BKIN logic-only capture: post-hoc analysis

The original `report.json` remains unchanged and reports `pass=false` because
its first-low-pulse criterion required at least 50 ms. The operator contact
bounced; that criterion was inappropriate for proving the break response.
The raw Saleae CSV is unchanged (SHA-256:
`B2381C5E43DC1A5505E4BD6AA70AF518B268602A84F901599E74CDF773736297`).

Reanalysis using the corrected `analyze_external_break()` passes all six
checks. The six PWM channels ran at about 10.025 kHz without pair overlap.
SD/PA6 first fell at 4.13230625 s; all six PWM outputs remained LOW from
0.5 us later. The SD contact produced 652 edges, 235.27 ms cumulative LOW
time, and returned HIGH by 4.69372775 s. No PWM restarted after release.
Nucleo reported fault 7 with PWM=0, and a START without CLEAR was rejected
(HTTP 409). The tool restored both production images. A subsequent Wi-Fi
status read showed SAFE, PWM=0, Vdc=0 V, UNO build 2026092901, and Nucleo
build 2026091401.

This proves the externally pulled-low TP23-to-Nucleo PA6/BKIN logic path and
timer shutdown in the low-voltage diagnostic image. J4 and the power input
were off. It does not prove an internally generated IPM SD fault with J4
powered, production-firmware PWM at a valid bus voltage, the external soft
start, or a motor run. The production release gate remains closed.
