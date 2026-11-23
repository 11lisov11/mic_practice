
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r6\fixture\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08009078 <PWM_SetPhasePWMOutputs>:
 8009078:	ee10 3a10 	vmov	r3, s0
 800907c:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8009080:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8009084:	d072      	beq.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 8009086:	ee10 3a90 	vmov	r3, s1
 800908a:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 800908e:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8009092:	d06b      	beq.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 8009094:	ee11 1a10 	vmov	r1, s2
 8009098:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 800909c:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 80090a0:	d064      	beq.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090a2:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 80090a6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090aa:	d45f      	bmi.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090ac:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 80090b0:	eeb4 0ae7 	vcmpe.f32	s0, s15
 80090b4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090b8:	dc58      	bgt.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090ba:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 80090be:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090c2:	d453      	bmi.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090c4:	eef4 0ae7 	vcmpe.f32	s1, s15
 80090c8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090cc:	dc4e      	bgt.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090ce:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 80090d2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090d6:	d449      	bmi.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090d8:	eeb4 1ae7 	vcmpe.f32	s2, s15
 80090dc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80090e0:	dc44      	bgt.n	800916c <PWM_SetPhasePWMOutputs+0xf4>
 80090e2:	b430      	push	{r4, r5}
 80090e4:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 80090e8:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090ea:	2a01      	cmp	r2, #1
 80090ec:	d940      	bls.n	8009170 <PWM_SetPhasePWMOutputs+0xf8>
 80090ee:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090f0:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 80090f4:	d23c      	bcs.n	8009170 <PWM_SetPhasePWMOutputs+0xf8>
 80090f6:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 80090f8:	3a01      	subs	r2, #1
 80090fa:	ee07 2a90 	vmov	s15, r2
 80090fe:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8009102:	ee67 7a80 	vmul.f32	s15, s15, s0
 8009106:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800910a:	ee17 2a90 	vmov	r2, s15
 800910e:	b294      	uxth	r4, r2
 8009110:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009112:	3a01      	subs	r2, #1
 8009114:	ee07 2a10 	vmov	s14, r2
 8009118:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 800911a:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 800911e:	1e53      	subs	r3, r2, #1
 8009120:	ee07 3a90 	vmov	s15, r3
 8009124:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009128:	eef8 7a67 	vcvt.f32.u32	s15, s15
 800912c:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009130:	ee67 7a81 	vmul.f32	s15, s15, s2
 8009134:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009138:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800913c:	ee17 2a10 	vmov	r2, s14
 8009140:	ee17 3a90 	vmov	r3, s15
 8009144:	b292      	uxth	r2, r2
 8009146:	b29b      	uxth	r3, r3
 8009148:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 800914c:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009150:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 8009154:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009158:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 800915c:	636c      	str	r4, [r5, #52]	@ 0x34
 800915e:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009160:	63eb      	str	r3, [r5, #60]	@ 0x3c
 8009162:	6928      	ldr	r0, [r5, #16]
 8009164:	f000 0001 	and.w	r0, r0, #1
 8009168:	bc30      	pop	{r4, r5}
 800916a:	4770      	bx	lr
 800916c:	2080      	movs	r0, #128	@ 0x80
 800916e:	4770      	bx	lr
 8009170:	2080      	movs	r0, #128	@ 0x80
 8009172:	e7f9      	b.n	8009168 <PWM_SetPhasePWMOutputs+0xf0>
