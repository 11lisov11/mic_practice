
artifacts/live_bench_20261014/pwm_filter_pair_r4/production/nucleo/STM32CubeIDE/Debug/ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08003e5c <TSK_HighFrequencyTask>:
 8003e5c:	b538      	push	{r3, r4, r5, lr}
 8003e5e:	4d13      	ldr	r5, [pc, #76]	@ (8003eac <TSK_HighFrequencyTask+0x50>)
 8003e60:	682b      	ldr	r3, [r5, #0]
 8003e62:	f8d3 3088 	ldr.w	r3, [r3, #136]	@ 0x88
 8003e66:	6c5b      	ldr	r3, [r3, #68]	@ 0x44
 8003e68:	041b      	lsls	r3, r3, #16
 8003e6a:	d510      	bpl.n	8003e8e <TSK_HighFrequencyTask+0x32>
 8003e6c:	4c10      	ldr	r4, [pc, #64]	@ (8003eb0 <TSK_HighFrequencyTask+0x54>)
 8003e6e:	6820      	ldr	r0, [r4, #0]
 8003e70:	f004 fc8e 	bl	8008790 <ACIM_VF_CalcAngle>
 8003e74:	6820      	ldr	r0, [r4, #0]
 8003e76:	f004 fd21 	bl	80088bc <ACIM_VF_Controller>
 8003e7a:	4604      	mov	r4, r0
 8003e7c:	b968      	cbnz	r0, 8003e9a <TSK_HighFrequencyTask+0x3e>
 8003e7e:	4a0d      	ldr	r2, [pc, #52]	@ (8003eb4 <TSK_HighFrequencyTask+0x58>)
 8003e80:	480d      	ldr	r0, [pc, #52]	@ (8003eb8 <TSK_HighFrequencyTask+0x5c>)
 8003e82:	6813      	ldr	r3, [r2, #0]
 8003e84:	f890 1029 	ldrb.w	r1, [r0, #41]	@ 0x29
 8003e88:	3301      	adds	r3, #1
 8003e8a:	6013      	str	r3, [r2, #0]
 8003e8c:	b909      	cbnz	r1, 8003e92 <TSK_HighFrequencyTask+0x36>
 8003e8e:	2000      	movs	r0, #0
 8003e90:	bd38      	pop	{r3, r4, r5, pc}
 8003e92:	f004 fe0f 	bl	8008ab4 <MCPA_dataLog>
 8003e96:	2000      	movs	r0, #0
 8003e98:	bd38      	pop	{r3, r4, r5, pc}
 8003e9a:	6828      	ldr	r0, [r5, #0]
 8003e9c:	f005 f8ee 	bl	800907c <PWM_SwitchOffPWM>
 8003ea0:	4806      	ldr	r0, [pc, #24]	@ (8003ebc <TSK_HighFrequencyTask+0x60>)
 8003ea2:	2200      	movs	r2, #0
 8003ea4:	4621      	mov	r1, r4
 8003ea6:	f7ff fc3f 	bl	8003728 <MCI_FaultProcessing>
 8003eaa:	e7e8      	b.n	8003e7e <TSK_HighFrequencyTask+0x22>
 8003eac:	20000a3c 	.word	0x20000a3c
 8003eb0:	20000a34 	.word	0x20000a34
 8003eb4:	20001c10 	.word	0x20001c10
 8003eb8:	20000274 	.word	0x20000274
 8003ebc:	20000a00 	.word	0x20000a00
