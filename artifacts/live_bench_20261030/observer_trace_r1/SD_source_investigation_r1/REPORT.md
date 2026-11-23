# SD source investigation without START

The exact physical source is not established. A shared SD wire and one GPIO observation cannot distinguish an IPM open-drain output from another load or a wiring fault.

The new snapshot records Break at native tick 0, MOE=0 and no valid cached context. It predates FOC START. Its BDTR has BKBID=0, BKE=1 and AOE=0. The fresh live configuration check passes. RM0440 defines BKBID=0 as input mode, so releasing a supposed bidirectional-output latch is not a justified fix.

The installed source reads GPIOA IDR PA6 directly. The prior software audit checked all 256 flag combinations and separation from the stored fault mask. No native Src PA11 output initialization was found; this does not exclude hardware loading.

An independent unpack of the original saved 320-byte dual capture reproduces 90993 nominal 200-ns samples of PA6 LOW while PA4 stayed HIGH. The old TP23-to-PA4 branch continuity was not independently confirmed, so this motivates checking the signal route and does not prove an IPM defect.

UM2014 page 7 gives R28=10 kohm and C20=330 pF: tau=3.3 us. This nominal healthy RC alone cannot explain minutes of LOW. The actual fitted components have not been verified. Current zero-ready and midscale offsets do not qualify internal driver VCCL or identify UVLO.

STGIB15CH60TS-L fault management lists CIN overcurrent and VCC undervoltage as internal SD fault sources; SD is also an external shutdown input. No complete current pulse waveform or independent active-source readout is available. Do not infer UVLO, CIN fault or intrinsic module damage from the current single LOW.

Requested one passive split: with J1/J4 OFF and controllers powered, unplug the 34-pin cable at STEVAL, leaving it on IHM09M2. Read PA6 only. HIGH localizes dependence on the STEVAL connection; LOW leaves cable/adapter/Nucleo. No START is permitted with the protection connection removed. No protection edits, RESET, CLEAR or flashing were performed. Old records remain unchanged.

Primary references:
- https://www.st.com/resource/en/reference_manual/dm00355726-stm32g4-series-advanced-arm-based-32-bit-mcus-stmicroelectronics.pdf (TIM1/TIM8/TIM20 BDTR BKBID)
- https://www.st.com/resource/en/datasheet/stgib15ch60ts-l.pdf (DS10424 Rev10 fault management)
- https://www.st.com/resource/en/schematic_pack/x-nucleo-ihm09m2_schematic.pdf
- Local UM2014 Rev3, pages 7 and 11.
