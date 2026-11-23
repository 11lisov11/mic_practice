
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r3\fixture\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08009068 <PWM_SetPhasePWMOutputs>:
 8009068:	ee10 3a10 	vmov	r3, s0
 800906c:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8009070:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8009074:	d072      	beq.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 8009076:	ee10 3a90 	vmov	r3, s1
 800907a:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 800907e:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8009082:	d06b      	beq.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 8009084:	ee11 1a10 	vmov	r1, s2
 8009088:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 800908c:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8009090:	d064      	beq.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 8009092:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 8009096:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800909a:	d45f      	bmi.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 800909c:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 80090a0:	eeb4 0ae7 	vcmpe.f32	s0, s15
 80090a4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090a8:	dc58      	bgt.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 80090aa:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 80090ae:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090b2:	d453      	bmi.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 80090b4:	eef4 0ae7 	vcmpe.f32	s1, s15
 80090b8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090bc:	dc4e      	bgt.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 80090be:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 80090c2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090c6:	d449      	bmi.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 80090c8:	eeb4 1ae7 	vcmpe.f32	s2, s15
 80090cc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090d0:	dc44      	bgt.n	800915c <PWM_SetPhasePWMOutputs+0xf4>
 80090d2:	b430      	push	{r4, r5}
 80090d4:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 80090d8:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090da:	2a01      	cmp	r2, #1
 80090dc:	d940      	bls.n	8009160 <PWM_SetPhasePWMOutputs+0xf8>
 80090de:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090e0:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 80090e4:	d23c      	bcs.n	8009160 <PWM_SetPhasePWMOutputs+0xf8>
 80090e6:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090e8:	3a01      	subs	r2, #1
 80090ea:	ee07 2a90 	vmov	s15, r2
 80090ee:	eef8 7a67 	vcvt.f32.u32	s15, s15
 80090f2:	ee67 7a80 	vmul.f32	s15, s15, s0
 80090f6:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 80090fa:	ee17 2a90 	vmov	r2, s15
 80090fe:	b294      	uxth	r4, r2
 8009100:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009102:	3a01      	subs	r2, #1
 8009104:	ee07 2a10 	vmov	s14, r2
 8009108:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 800910a:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 800910e:	1e53      	subs	r3, r2, #1
 8009110:	ee07 3a90 	vmov	s15, r3
 8009114:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009118:	eef8 7a67 	vcvt.f32.u32	s15, s15
 800911c:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009120:	ee67 7a81 	vmul.f32	s15, s15, s2
 8009124:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009128:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800912c:	ee17 2a10 	vmov	r2, s14
 8009130:	ee17 3a90 	vmov	r3, s15
 8009134:	b292      	uxth	r2, r2
 8009136:	b29b      	uxth	r3, r3
 8009138:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 800913c:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009140:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 8009144:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009148:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 800914c:	636c      	str	r4, [r5, #52]	@ 0x34
 800914e:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009150:	63eb      	str	r3, [r5, #60]	@ 0x3c
 8009152:	6928      	ldr	r0, [r5, #16]
 8009154:	f000 0001 	and.w	r0, r0, #1
 8009158:	bc30      	pop	{r4, r5}
 800915a:	4770      	bx	lr
 800915c:	2080      	movs	r0, #128	@ 0x80
 800915e:	4770      	bx	lr
 8009160:	2080      	movs	r0, #128	@ 0x80
 8009162:	e7f9      	b.n	8009158 <PWM_SetPhasePWMOutputs+0xf0>
