
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r7\fixture\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

080090b0 <PWM_SetPhasePWMOutputs>:
 80090b0:	ee10 3a10 	vmov	r3, s0
 80090b4:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 80090b8:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 80090bc:	d072      	beq.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090be:	ee10 3a90 	vmov	r3, s1
 80090c2:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 80090c6:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 80090ca:	d06b      	beq.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090cc:	ee11 1a10 	vmov	r1, s2
 80090d0:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 80090d4:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 80090d8:	d064      	beq.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090da:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 80090de:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090e2:	d45f      	bmi.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090e4:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 80090e8:	eeb4 0ae7 	vcmpe.f32	s0, s15
 80090ec:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090f0:	dc58      	bgt.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090f2:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 80090f6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090fa:	d453      	bmi.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 80090fc:	eef4 0ae7 	vcmpe.f32	s1, s15
 8009100:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8009104:	dc4e      	bgt.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 8009106:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 800910a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800910e:	d449      	bmi.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 8009110:	eeb4 1ae7 	vcmpe.f32	s2, s15
 8009114:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8009118:	dc44      	bgt.n	80091a4 <PWM_SetPhasePWMOutputs+0xf4>
 800911a:	b430      	push	{r4, r5}
 800911c:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 8009120:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009122:	2a01      	cmp	r2, #1
 8009124:	d940      	bls.n	80091a8 <PWM_SetPhasePWMOutputs+0xf8>
 8009126:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009128:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 800912c:	d23c      	bcs.n	80091a8 <PWM_SetPhasePWMOutputs+0xf8>
 800912e:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009130:	3a01      	subs	r2, #1
 8009132:	ee07 2a90 	vmov	s15, r2
 8009136:	eef8 7a67 	vcvt.f32.u32	s15, s15
 800913a:	ee67 7a80 	vmul.f32	s15, s15, s0
 800913e:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 8009142:	ee17 2a90 	vmov	r2, s15
 8009146:	b294      	uxth	r4, r2
 8009148:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 800914a:	3a01      	subs	r2, #1
 800914c:	ee07 2a10 	vmov	s14, r2
 8009150:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009152:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 8009156:	1e53      	subs	r3, r2, #1
 8009158:	ee07 3a90 	vmov	s15, r3
 800915c:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009160:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8009164:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009168:	ee67 7a81 	vmul.f32	s15, s15, s2
 800916c:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009170:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 8009174:	ee17 2a10 	vmov	r2, s14
 8009178:	ee17 3a90 	vmov	r3, s15
 800917c:	b292      	uxth	r2, r2
 800917e:	b29b      	uxth	r3, r3
 8009180:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 8009184:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009188:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 800918c:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009190:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 8009194:	636c      	str	r4, [r5, #52]	@ 0x34
 8009196:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009198:	63eb      	str	r3, [r5, #60]	@ 0x3c
 800919a:	6928      	ldr	r0, [r5, #16]
 800919c:	f000 0001 	and.w	r0, r0, #1
 80091a0:	bc30      	pop	{r4, r5}
 80091a2:	4770      	bx	lr
 80091a4:	2080      	movs	r0, #128	@ 0x80
 80091a6:	4770      	bx	lr
 80091a8:	2080      	movs	r0, #128	@ 0x80
 80091aa:	e7f9      	b.n	80091a0 <PWM_SetPhasePWMOutputs+0xf0>
