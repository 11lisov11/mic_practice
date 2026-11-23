
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r7\fixture\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

08008a0c <ACIM_VF_Controller>:
 8008a0c:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 8008a10:	ee17 3a90 	vmov	r3, s15
 8008a14:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 8008a18:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 8008a1c:	f000 80e1 	beq.w	8008be2 <ACIM_VF_Controller+0x1d6>
 8008a20:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 8008a24:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a28:	f240 80db 	bls.w	8008be2 <ACIM_VF_Controller+0x1d6>
 8008a2c:	b510      	push	{r4, lr}
 8008a2e:	69c2      	ldr	r2, [r0, #28]
 8008a30:	ed2d 8b04 	vpush	{d8-d9}
 8008a34:	f002 43ff 	and.w	r3, r2, #2139095040	@ 0x7f800000
 8008a38:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 8008a3c:	b086      	sub	sp, #24
 8008a3e:	4604      	mov	r4, r0
 8008a40:	f000 80ca 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a44:	6a43      	ldr	r3, [r0, #36]	@ 0x24
 8008a46:	f003 41ff 	and.w	r1, r3, #2139095040	@ 0x7f800000
 8008a4a:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a4e:	f000 80c3 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a52:	edd0 6a04 	vldr	s13, [r0, #16]
 8008a56:	ee16 1a90 	vmov	r1, s13
 8008a5a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a5e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a62:	f000 80b9 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a66:	eef5 6ac0 	vcmpe.f32	s13, #0.0
 8008a6a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a6e:	f100 80b3 	bmi.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a72:	edd0 5a06 	vldr	s11, [r0, #24]
 8008a76:	ee15 1a90 	vmov	r1, s11
 8008a7a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a7e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008a82:	f000 80a9 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a86:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 8008a8a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a8e:	f100 80a3 	bmi.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008a92:	ed90 6a05 	vldr	s12, [r0, #20]
 8008a96:	ee16 1a10 	vmov	r1, s12
 8008a9a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008a9e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008aa2:	f000 8099 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008aa6:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 8008aaa:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008aae:	f100 8093 	bmi.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008ab2:	ed90 9a02 	vldr	s18, [r0, #8]
 8008ab6:	ee19 1a10 	vmov	r1, s18
 8008aba:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008abe:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008ac2:	f000 8089 	beq.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008ac6:	eeb5 9ac0 	vcmpe.f32	s18, #0.0
 8008aca:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008ace:	f240 8083 	bls.w	8008bd8 <ACIM_VF_Controller+0x1cc>
 8008ad2:	ee07 2a10 	vmov	s14, r2
 8008ad6:	eeb0 7ac7 	vabs.f32	s14, s14
 8008ada:	eef4 5ac7 	vcmpe.f32	s11, s14
 8008ade:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008ae2:	d805      	bhi.n	8008af0 <ACIM_VF_Controller+0xe4>
 8008ae4:	ed9f 6a40 	vldr	s12, [pc, #256]	@ 8008be8 <ACIM_VF_Controller+0x1dc>
 8008ae8:	ee66 6a86 	vmul.f32	s13, s13, s12
 8008aec:	ee26 6a87 	vmul.f32	s12, s13, s14
 8008af0:	eeb4 9ac6 	vcmpe.f32	s18, s12
 8008af4:	ed9f 7a3d 	vldr	s14, [pc, #244]	@ 8008bec <ACIM_VF_Controller+0x1e0>
 8008af8:	ee06 3a90 	vmov	s13, r3
 8008afc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b00:	bf58      	it	pl
 8008b02:	eeb0 9a46 	vmovpl.f32	s18, s12
 8008b06:	ee26 8a87 	vmul.f32	s16, s13, s14
 8008b0a:	eef4 7ac9 	vcmpe.f32	s15, s18
 8008b0e:	bf48      	it	mi
 8008b10:	eeb0 6a49 	vmovmi.f32	s12, s18
 8008b14:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b18:	bf54      	ite	pl
 8008b1a:	ed84 6a03 	vstrpl	s12, [r4, #12]
 8008b1e:	edc4 7a03 	vstrmi	s15, [r4, #12]
 8008b22:	eeb0 0a48 	vmov.f32	s0, s16
 8008b26:	bf48      	it	mi
 8008b28:	eeb0 9a67 	vmovmi.f32	s18, s15
 8008b2c:	f7fa fe8a 	bl	8003844 <MCM_floatTrig_Functions>
 8008b30:	eddf 7a2f 	vldr	s15, [pc, #188]	@ 8008bf0 <ACIM_VF_Controller+0x1e4>
 8008b34:	edd4 9a03 	vldr	s19, [r4, #12]
 8008b38:	eef0 8a40 	vmov.f32	s17, s0
 8008b3c:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008b40:	f7fa fe80 	bl	8003844 <MCM_floatTrig_Functions>
 8008b44:	eddf 7a2b 	vldr	s15, [pc, #172]	@ 8008bf4 <ACIM_VF_Controller+0x1e8>
 8008b48:	ee69 9a80 	vmul.f32	s19, s19, s0
 8008b4c:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008b50:	ed94 8a03 	vldr	s16, [r4, #12]
 8008b54:	f7fa fe76 	bl	8003844 <MCM_floatTrig_Functions>
 8008b58:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 8008b5c:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 8008b60:	eec6 5a27 	vdiv.f32	s11, s12, s15
 8008b64:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 8008b68:	ee65 7aa8 	vmul.f32	s15, s11, s17
 8008b6c:	ee65 6aa9 	vmul.f32	s13, s11, s19
 8008b70:	ee67 7a89 	vmul.f32	s15, s15, s18
 8008b74:	ee28 7a00 	vmul.f32	s14, s16, s0
 8008b78:	eef4 7ac6 	vcmpe.f32	s15, s12
 8008b7c:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b80:	bfdc      	itt	le
 8008b82:	ee77 7a86 	vaddle.f32	s15, s15, s12
 8008b86:	eeb6 0a00 	vmovle.f32	s0, #96	@ 0x3f000000  0.5
 8008b8a:	eef4 6ae0 	vcmpe.f32	s13, s1
 8008b8e:	bfd4      	ite	le
 8008b90:	ee27 0a80 	vmulle.f32	s0, s15, s0
 8008b94:	eeb0 0a46 	vmovgt.f32	s0, s12
 8008b98:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008b9c:	ee27 7a25 	vmul.f32	s14, s14, s11
 8008ba0:	dc05      	bgt.n	8008bae <ACIM_VF_Controller+0x1a2>
 8008ba2:	ee76 6aa0 	vadd.f32	s13, s13, s1
 8008ba6:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 8008baa:	ee66 0aa0 	vmul.f32	s1, s13, s1
 8008bae:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 8008bb2:	eeb4 7ac1 	vcmpe.f32	s14, s2
 8008bb6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008bba:	dc05      	bgt.n	8008bc8 <ACIM_VF_Controller+0x1bc>
 8008bbc:	ee37 7a01 	vadd.f32	s14, s14, s2
 8008bc0:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 8008bc4:	ee27 1a01 	vmul.f32	s2, s14, s2
 8008bc8:	6860      	ldr	r0, [r4, #4]
 8008bca:	b006      	add	sp, #24
 8008bcc:	ecbd 8b04 	vpop	{d8-d9}
 8008bd0:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 8008bd4:	f000 ba6c 	b.w	80090b0 <PWM_SetPhasePWMOutputs>
 8008bd8:	2080      	movs	r0, #128	@ 0x80
 8008bda:	b006      	add	sp, #24
 8008bdc:	ecbd 8b04 	vpop	{d8-d9}
 8008be0:	bd10      	pop	{r4, pc}
 8008be2:	2080      	movs	r0, #128	@ 0x80
 8008be4:	4770      	bx	lr
 8008be6:	bf00      	nop
 8008be8:	40c90fdb 	.word	0x40c90fdb
 8008bec:	42652ee0 	.word	0x42652ee0
 8008bf0:	43700000 	.word	0x43700000
 8008bf4:	42f00000 	.word	0x42f00000
