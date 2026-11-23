
C:\mic_practice\artifacts\live_bench_20261118\boot_stack_integrity_r1\build\uno\UNOQ_MOTOR.ino.elf:     file format elf32-littlearm


Disassembly of section .text:

00012398 <_ZN7arduino12ZephyrSerial17availableForWriteEv>:
   12398:	b538      	push	{r3, r4, r5, lr}
   1239a:	4604      	mov	r4, r0
   1239c:	f100 0568 	add.w	r5, r0, #104	@ 0x68
   123a0:	4628      	mov	r0, r5
   123a2:	4908      	ldr	r1, [pc, #32]	@ (123c4 <_ZN7arduino12ZephyrSerial17availableForWriteEv+0x2c>)
   123a4:	f04f 32ff 	mov.w	r2, #4294967295
   123a8:	f04f 33ff 	mov.w	r3, #4294967295
   123ac:	4788      	blx	r1
   123ae:	8c22      	ldrh	r2, [r4, #32]
   123b0:	8b23      	ldrh	r3, [r4, #24]
   123b2:	6a64      	ldr	r4, [r4, #36]	@ 0x24
   123b4:	1a9b      	subs	r3, r3, r2
   123b6:	b29b      	uxth	r3, r3
   123b8:	4628      	mov	r0, r5
   123ba:	1ae4      	subs	r4, r4, r3
   123bc:	4b02      	ldr	r3, [pc, #8]	@ (123c8 <_ZN7arduino12ZephyrSerial17availableForWriteEv+0x30>)
   123be:	4798      	blx	r3
   123c0:	4620      	mov	r0, r4
   123c2:	bd38      	pop	{r3, r4, r5, pc}
	...
