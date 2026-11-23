
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r3\fixture\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

080089c4 <ACIM_VF_Controller>:
 80089c4:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 80089c8:	ee17 3a90 	vmov	r3, s15
 80089cc:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 80089d0:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80089d4:	f000 80e1 	beq.w	8008b9a <ACIM_VF_Controller+0x1d6>
 80089d8:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 80089dc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089e0:	f240 80db 	bls.w	8008b9a <ACIM_VF_Controller+0x1d6>
 80089e4:	b510      	push	{r4, lr}
 80089e6:	69c2      	ldr	r2, [r0, #28]
 80089e8:	ed2d 8b04 	vpush	{d8-d9}
 80089ec:	f002 43ff 	and.w	r3, r2, #2139095040	@ 0x7f800000
 80089f0:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80089f4:	b086      	sub	sp, #24
 80089f6:	4604      	mov	r4, r0
 80089f8:	f000 80ca 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 80089fc:	6a43      	ldr	r3, [r0, #36]	@ 0x24
 80089fe:	f003 41ff 	and.w	r1, r3, #2139095040	@ 0x7f800000
 8008a02:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a06:	f000 80c3 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a0a:	edd0 6a04 	vldr	s13, [r0, #16]
 8008a0e:	ee16 1a90 	vmov	r1, s13
 8008a12:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a16:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a1a:	f000 80b9 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a1e:	eef5 6ac0 	vcmpe.f32	s13, #0.0
 8008a22:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a26:	f100 80b3 	bmi.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a2a:	edd0 5a06 	vldr	s11, [r0, #24]
 8008a2e:	ee15 1a90 	vmov	r1, s11
 8008a32:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a36:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a3a:	f000 80a9 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a3e:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 8008a42:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a46:	f100 80a3 	bmi.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a4a:	ed90 6a05 	vldr	s12, [r0, #20]
 8008a4e:	ee16 1a10 	vmov	r1, s12
 8008a52:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a56:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a5a:	f000 8099 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a5e:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 8008a62:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a66:	f100 8093 	bmi.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a6a:	ed90 9a02 	vldr	s18, [r0, #8]
 8008a6e:	ee19 1a10 	vmov	r1, s18
 8008a72:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a76:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a7a:	f000 8089 	beq.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a7e:	eeb5 9ac0 	vcmpe.f32	s18, #0.0
 8008a82:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a86:	f240 8083 	bls.w	8008b90 <ACIM_VF_Controller+0x1cc>
 8008a8a:	ee07 2a10 	vmov	s14, r2
 8008a8e:	eeb0 7ac7 	vabs.f32	s14, s14
 8008a92:	eef4 5ac7 	vcmpe.f32	s11, s14
 8008a96:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a9a:	d805      	bhi.n	8008aa8 <ACIM_VF_Controller+0xe4>
 8008a9c:	ed9f 6a40 	vldr	s12, [pc, #256]	@ 8008ba0 <ACIM_VF_Controller+0x1dc>
 8008aa0:	ee66 6a86 	vmul.f32	s13, s13, s12
 8008aa4:	ee26 6a87 	vmul.f32	s12, s13, s14
 8008aa8:	eeb4 9ac6 	vcmpe.f32	s18, s12
 8008aac:	ed9f 7a3d 	vldr	s14, [pc, #244]	@ 8008ba4 <ACIM_VF_Controller+0x1e0>
 8008ab0:	ee06 3a90 	vmov	s13, r3
 8008ab4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008ab8:	bf58      	it	pl
 8008aba:	eeb0 9a46 	vmovpl.f32	s18, s12
 8008abe:	ee26 8a87 	vmul.f32	s16, s13, s14
 8008ac2:	eef4 7ac9 	vcmpe.f32	s15, s18
 8008ac6:	bf48      	it	mi
 8008ac8:	eeb0 6a49 	vmovmi.f32	s12, s18
 8008acc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008ad0:	bf54      	ite	pl
 8008ad2:	ed84 6a03 	vstrpl	s12, [r4, #12]
 8008ad6:	edc4 7a03 	vstrmi	s15, [r4, #12]
 8008ada:	eeb0 0a48 	vmov.f32	s0, s16
 8008ade:	bf48      	it	mi
 8008ae0:	eeb0 9a67 	vmovmi.f32	s18, s15
 8008ae4:	f7fa fe92 	bl	800380c <MCM_floatTrig_Functions>
 8008ae8:	eddf 7a2f 	vldr	s15, [pc, #188]	@ 8008ba8 <ACIM_VF_Controller+0x1e4>
 8008aec:	edd4 9a03 	vldr	s19, [r4, #12]
 8008af0:	eef0 8a40 	vmov.f32	s17, s0
 8008af4:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008af8:	f7fa fe88 	bl	800380c <MCM_floatTrig_Functions>
 8008afc:	eddf 7a2b 	vldr	s15, [pc, #172]	@ 8008bac <ACIM_VF_Controller+0x1e8>
 8008b00:	ee69 9a80 	vmul.f32	s19, s19, s0
 8008b04:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008b08:	ed94 8a03 	vldr	s16, [r4, #12]
 8008b0c:	f7fa fe7e 	bl	800380c <MCM_floatTrig_Functions>
 8008b10:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 8008b14:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 8008b18:	eec6 5a27 	vdiv.f32	s11, s12, s15
 8008b1c:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 8008b20:	ee65 7aa8 	vmul.f32	s15, s11, s17
 8008b24:	ee65 6aa9 	vmul.f32	s13, s11, s19
 8008b28:	ee67 7a89 	vmul.f32	s15, s15, s18
 8008b2c:	ee28 7a00 	vmul.f32	s14, s16, s0
 8008b30:	eef4 7ac6 	vcmpe.f32	s15, s12
 8008b34:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b38:	bfdc      	itt	le
 8008b3a:	ee77 7a86 	vaddle.f32	s15, s15, s12
 8008b3e:	eeb6 0a00 	vmovle.f32	s0, #96	@ 0x3f000000  0.5
 8008b42:	eef4 6ae0 	vcmpe.f32	s13, s1
 8008b46:	bfd4      	ite	le
 8008b48:	ee27 0a80 	vmulle.f32	s0, s15, s0
 8008b4c:	eeb0 0a46 	vmovgt.f32	s0, s12
 8008b50:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b54:	ee27 7a25 	vmul.f32	s14, s14, s11
 8008b58:	dc05      	bgt.n	8008b66 <ACIM_VF_Controller+0x1a2>
 8008b5a:	ee76 6aa0 	vadd.f32	s13, s13, s1
 8008b5e:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 8008b62:	ee66 0aa0 	vmul.f32	s1, s13, s1
 8008b66:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 8008b6a:	eeb4 7ac1 	vcmpe.f32	s14, s2
 8008b6e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b72:	dc05      	bgt.n	8008b80 <ACIM_VF_Controller+0x1bc>
 8008b74:	ee37 7a01 	vadd.f32	s14, s14, s2
 8008b78:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 8008b7c:	ee27 1a01 	vmul.f32	s2, s14, s2
 8008b80:	6860      	ldr	r0, [r4, #4]
 8008b82:	b006      	add	sp, #24
 8008b84:	ecbd 8b04 	vpop	{d8-d9}
 8008b88:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 8008b8c:	f000 ba6c 	b.w	8009068 <PWM_SetPhasePWMOutputs>
 8008b90:	2080      	movs	r0, #128	@ 0x80
 8008b92:	b006      	add	sp, #24
 8008b94:	ecbd 8b04 	vpop	{d8-d9}
 8008b98:	bd10      	pop	{r4, pc}
 8008b9a:	2080      	movs	r0, #128	@ 0x80
 8008b9c:	4770      	bx	lr
 8008b9e:	bf00      	nop
 8008ba0:	40c90fdb 	.word	0x40c90fdb
 8008ba4:	42652ee0 	.word	0x42652ee0
 8008ba8:	43700000 	.word	0x43700000
 8008bac:	42f00000 	.word	0x42f00000
