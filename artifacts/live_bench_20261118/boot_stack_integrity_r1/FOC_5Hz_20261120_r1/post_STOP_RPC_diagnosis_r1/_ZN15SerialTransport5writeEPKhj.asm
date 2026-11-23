
C:\mic_practice\artifacts\live_bench_20261118\boot_stack_integrity_r1\build\uno\UNOQ_MOTOR.ino.elf:     file format elf32-littlearm


Disassembly of section .text:

0000001a <_ZN15SerialTransport5writeEPKhj>:
      1a:	b570      	push	{r4, r5, r6, lr}
      1c:	4604      	mov	r4, r0
      1e:	6840      	ldr	r0, [r0, #4]
      20:	4616      	mov	r6, r2
      22:	6803      	ldr	r3, [r0, #0]
      24:	460d      	mov	r5, r1
      26:	689b      	ldr	r3, [r3, #8]
      28:	4798      	blx	r3
      2a:	1e02      	subs	r2, r0, #0
      2c:	dd0a      	ble.n	44 <_ZN15SerialTransport5writeEPKhj+0x2a>
      2e:	6860      	ldr	r0, [r4, #4]
      30:	42b2      	cmp	r2, r6
      32:	6803      	ldr	r3, [r0, #0]
      34:	bf28      	it	cs
      36:	4632      	movcs	r2, r6
      38:	685c      	ldr	r4, [r3, #4]
      3a:	4629      	mov	r1, r5
      3c:	4623      	mov	r3, r4
      3e:	e8bd 4070 	ldmia.w	sp!, {r4, r5, r6, lr}
      42:	4718      	bx	r3
      44:	2000      	movs	r0, #0
      46:	bd70      	pop	{r4, r5, r6, pc}
