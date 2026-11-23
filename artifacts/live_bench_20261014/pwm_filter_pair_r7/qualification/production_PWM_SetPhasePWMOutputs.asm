
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r7\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08008f98 <PWM_SetPhasePWMOutputs>:
 8008f98:	ee10 3a10 	vmov	r3, s0
 8008f9c:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008fa0:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008fa4:	d072      	beq.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fa6:	ee10 3a90 	vmov	r3, s1
 8008faa:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 8008fae:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008fb2:	d06b      	beq.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fb4:	ee11 1a10 	vmov	r1, s2
 8008fb8:	f001 42ff 	and.w	r2, r1, #2139095040	@ 0x7f800000
 8008fbc:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 8008fc0:	d064      	beq.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fc2:	eeb5 0ac0 	vcmpe.f32	s0, #0.0
 8008fc6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fca:	d45f      	bmi.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fcc:	eef7 7a00 	vmov.f32	s15, #112	@ 0x3f800000  1.0
 8008fd0:	eeb4 0ae7 	vcmpe.f32	s0, s15
 8008fd4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fd8:	dc58      	bgt.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fda:	eef5 0ac0 	vcmpe.f32	s1, #0.0
 8008fde:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fe2:	d453      	bmi.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fe4:	eef4 0ae7 	vcmpe.f32	s1, s15
 8008fe8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008fec:	dc4e      	bgt.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008fee:	eeb5 1ac0 	vcmpe.f32	s2, #0.0
 8008ff2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008ff6:	d449      	bmi.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8008ff8:	eeb4 1ae7 	vcmpe.f32	s2, s15
 8008ffc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8009000:	dc44      	bgt.n	800908c <PWM_SetPhasePWMOutputs+0xf4>
 8009002:	b430      	push	{r4, r5}
 8009004:	f8d0 5088 	ldr.w	r5, [r0, #136]	@ 0x88
 8009008:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 800900a:	2a01      	cmp	r2, #1
 800900c:	d940      	bls.n	8009090 <PWM_SetPhasePWMOutputs+0xf8>
 800900e:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009010:	f5b2 3f80 	cmp.w	r2, #65536	@ 0x10000
 8009014:	d23c      	bcs.n	8009090 <PWM_SetPhasePWMOutputs+0xf8>
 8009016:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009018:	3a01      	subs	r2, #1
 800901a:	ee07 2a90 	vmov	s15, r2
 800901e:	eef8 7a67 	vcvt.f32.u32	s15, s15
 8009022:	ee67 7a80 	vmul.f32	s15, s15, s0
 8009026:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800902a:	ee17 2a90 	vmov	r2, s15
 800902e:	b294      	uxth	r4, r2
 8009030:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 8009032:	3a01      	subs	r2, #1
 8009034:	ee07 2a10 	vmov	s14, r2
 8009038:	6aea      	ldr	r2, [r5, #44]	@ 0x2c
 800903a:	edc0 0a26 	vstr	s1, [r0, #152]	@ 0x98
 800903e:	1e53      	subs	r3, r2, #1
 8009040:	ee07 3a90 	vmov	s15, r3
 8009044:	eeb8 7a47 	vcvt.f32.u32	s14, s14
 8009048:	eef8 7a67 	vcvt.f32.u32	s15, s15
 800904c:	ee27 7a20 	vmul.f32	s14, s14, s1
 8009050:	ee67 7a81 	vmul.f32	s15, s15, s2
 8009054:	eebc 7ac7 	vcvt.u32.f32	s14, s14
 8009058:	eefc 7ae7 	vcvt.u32.f32	s15, s15
 800905c:	ee17 2a10 	vmov	r2, s14
 8009060:	ee17 3a90 	vmov	r3, s15
 8009064:	b292      	uxth	r2, r2
 8009066:	b29b      	uxth	r3, r3
 8009068:	ed80 0a25 	vstr	s0, [r0, #148]	@ 0x94
 800906c:	ed80 1a27 	vstr	s2, [r0, #156]	@ 0x9c
 8009070:	f8a0 40a0 	strh.w	r4, [r0, #160]	@ 0xa0
 8009074:	f8a0 30a4 	strh.w	r3, [r0, #164]	@ 0xa4
 8009078:	f8a0 20a2 	strh.w	r2, [r0, #162]	@ 0xa2
 800907c:	636c      	str	r4, [r5, #52]	@ 0x34
 800907e:	63aa      	str	r2, [r5, #56]	@ 0x38
 8009080:	63eb      	str	r3, [r5, #60]	@ 0x3c
 8009082:	6928      	ldr	r0, [r5, #16]
 8009084:	f000 0001 	and.w	r0, r0, #1
 8009088:	bc30      	pop	{r4, r5}
 800908a:	4770      	bx	lr
 800908c:	2080      	movs	r0, #128	@ 0x80
 800908e:	4770      	bx	lr
 8009090:	2080      	movs	r0, #128	@ 0x80
 8009092:	e7f9      	b.n	8009088 <PWM_SetPhasePWMOutputs+0xf0>
