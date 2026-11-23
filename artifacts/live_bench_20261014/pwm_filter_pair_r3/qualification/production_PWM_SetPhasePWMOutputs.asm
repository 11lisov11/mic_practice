
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r3\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08008f58 <PWM_SetPhasePWMOutputs>:
 8008f58:	ee10 3a10 	vmov	r3, s0
 8008f5c:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008f60:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f64:	d072      	beq.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008f66:	ee10 3a90 	vmov	r3, s1
 8008f6a:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008f6e:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f72:	d06b      	beq.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008f74:	ee11 1a10 	vmov	r1, s2
 8008f78:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 8008f7c:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f80:	d064      	beq.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008f82:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 8008f86:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008f8a:	d45f      	bmi.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008f8c:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 8008f90:	eeb4 0ae7 	vcmpe.f32	s0, s15
 8008f94:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008f98:	dc58      	bgt.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008f9a:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 8008f9e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fa2:	d453      	bmi.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008fa4:	eef4 0ae7 	vcmpe.f32	s1, s15
 8008fa8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fac:	dc4e      	bgt.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008fae:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 8008fb2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fb6:	d449      	bmi.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008fb8:	eeb4 1ae7 	vcmpe.f32	s2, s15
 8008fbc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fc0:	dc44      	bgt.n	800904c <PWM_SetPhasePWMOutputs+0xf4>
 8008fc2:	b430      	push	{r4, r5}
 8008fc4:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 8008fc8:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fca:	2a01      	cmp	r2, #1
 8008fcc:	d940      	bls.n	8009050 <PWM_SetPhasePWMOutputs+0xf8>
 8008fce:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fd0:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 8008fd4:	d23c      	bcs.n	8009050 <PWM_SetPhasePWMOutputs+0xf8>
 8008fd6:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fd8:	3a01      	subs	r2, #1
 8008fda:	ee07 2a90 	vmov	s15, r2
 8008fde:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8008fe2:	ee67 7a80 	vmul.f32	s15, s15, s0
 8008fe6:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 8008fea:	ee17 2a90 	vmov	r2, s15
 8008fee:	b294      	uxth	r4, r2
 8008ff0:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008ff2:	3a01      	subs	r2, #1
 8008ff4:	ee07 2a10 	vmov	s14, r2
 8008ff8:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008ffa:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 8008ffe:	1e53      	subs	r3, r2, #1
 8009000:	ee07 3a90 	vmov	s15, r3
 8009004:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009008:	eef8 7a67 	vcvt.f32.u32	s15, s15
 800900c:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009010:	ee67 7a81 	vmul.f32	s15, s15, s2
 8009014:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009018:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800901c:	ee17 2a10 	vmov	r2, s14
 8009020:	ee17 3a90 	vmov	r3, s15
 8009024:	b292      	uxth	r2, r2
 8009026:	b29b      	uxth	r3, r3
 8009028:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 800902c:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009030:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 8009034:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009038:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 800903c:	636c      	str	r4, [r5, #52]	@ 0x34
 800903e:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009040:	63eb      	str	r3, [r5, #60]	@ 0x3c
 8009042:	6928      	ldr	r0, [r5, #16]
 8009044:	f000 0001 	and.w	r0, r0, #1
 8009048:	bc30      	pop	{r4, r5}
 800904a:	4770      	bx	lr
 800904c:	2080      	movs	r0, #128	@ 0x80
 800904e:	4770      	bx	lr
 8009050:	2080      	movs	r0, #128	@ 0x80
 8009052:	e7f9      	b.n	8009048 <PWM_SetPhasePWMOutputs+0xf0>
