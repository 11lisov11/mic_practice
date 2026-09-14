# Isolated G431 logic test

NEVER CONNECT AN IPM, INVERTER, MOTOR OR DC BUS TO THIS IMAGE.
This diagnostic is not included in ready_to_flash and is not a motor-control firmware.

Uses the established G431 TIM1 routing: PA8/PA7, PA9/PB0, PA10/PB1.
At boot all outputs are low. An explicit SWD write of 0x504D5744 to
the ELF symbol diag_request starts exactly one 300 ms burst per reset.
TIM2 interrupt disables TIM1 outputs; a software deadline and independent
watchdog provide additional stop mechanisms. UART is not configured.

170 MHz HSI/PLL, center-aligned 16 kHz nominal, CKD=2, DTG=114
(228/170 MHz = 1.341 us nominal), duty commands 20/50/80 percent.
The physical high times are reduced by dead-time. This test checks pins,
carrier and complementary dead-time, not the complete MCSDK safety chain.

Build: `pio run -d nucleo_g431_pwm_diag_pio`

After testing, restore and verify the normal MCSDK firmware and capture all-low
outputs. Never leave this diagnostic installed for a later power-stage test.
