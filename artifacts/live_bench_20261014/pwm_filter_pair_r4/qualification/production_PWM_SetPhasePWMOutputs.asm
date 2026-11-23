
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r4\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08008f60 <PWM_SetPhasePWMOutputs>:
 8008f60:	ee10 3a10 	vmov	r3, s0
 8008f64:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008f68:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f6c:	d072      	beq.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008f6e:	ee10 3a90 	vmov	r3, s1
 8008f72:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008f76:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f7a:	d06b      	beq.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008f7c:	ee11 1a10 	vmov	r1, s2
 8008f80:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 8008f84:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008f88:	d064      	beq.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008f8a:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 8008f8e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008f92:	d45f      	bmi.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008f94:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 8008f98:	eeb4 0ae7 	vcmpe.f32	s0, s15
 8008f9c:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fa0:	dc58      	bgt.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008fa2:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 8008fa6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008faa:	d453      	bmi.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008fac:	eef4 0ae7 	vcmpe.f32	s1, s15
 8008fb0:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fb4:	dc4e      	bgt.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008fb6:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 8008fba:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fbe:	d449      	bmi.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008fc0:	eeb4 1ae7 	vcmpe.f32	s2, s15
 8008fc4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fc8:	dc44      	bgt.n	8009054 <PWM_SetPhasePWMOutputs+0xf4>
 8008fca:	b430      	push	{r4, r5}
 8008fcc:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 8008fd0:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fd2:	2a01      	cmp	r2, #1
 8008fd4:	d940      	bls.n	8009058 <PWM_SetPhasePWMOutputs+0xf8>
 8008fd6:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fd8:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 8008fdc:	d23c      	bcs.n	8009058 <PWM_SetPhasePWMOutputs+0xf8>
 8008fde:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008fe0:	3a01      	subs	r2, #1
 8008fe2:	ee07 2a90 	vmov	s15, r2
 8008fe6:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8008fea:	ee67 7a80 	vmul.f32	s15, s15, s0
 8008fee:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 8008ff2:	ee17 2a90 	vmov	r2, s15
 8008ff6:	b294      	uxth	r4, r2
 8008ff8:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8008ffa:	3a01      	subs	r2, #1
 8008ffc:	ee07 2a10 	vmov	s14, r2
 8009000:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009002:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 8009006:	1e53      	subs	r3, r2, #1
 8009008:	ee07 3a90 	vmov	s15, r3
 800900c:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009010:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8009014:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009018:	ee67 7a81 	vmul.f32	s15, s15, s2
 800901c:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009020:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 8009024:	ee17 2a10 	vmov	r2, s14
 8009028:	ee17 3a90 	vmov	r3, s15
 800902c:	b292      	uxth	r2, r2
 800902e:	b29b      	uxth	r3, r3
 8009030:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 8009034:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009038:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 800903c:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009040:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 8009044:	636c      	str	r4, [r5, #52]	@ 0x34
 8009046:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009048:	63eb      	str	r3, [r5, #60]	@ 0x3c
 800904a:	6928      	ldr	r0, [r5, #16]
 800904c:	f000 0001 	and.w	r0, r0, #1
 8009050:	bc30      	pop	{r4, r5}
 8009052:	4770      	bx	lr
 8009054:	2080      	movs	r0, #128	@ 0x80
 8009056:	4770      	bx	lr
 8009058:	2080      	movs	r0, #128	@ 0x80
 800905a:	e7f9      	b.n	8009050 <PWM_SetPhasePWMOutputs+0xf0>
