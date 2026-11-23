
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r4\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

080088bc <ACIM_VF_Controller>:
 80088bc:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 80088c0:	ee17 3a90 	vmov	r3, s15
 80088c4:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 80088c8:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80088cc:	f000 80e1 	beq.w	8008a92 <ACIM_VF_Controller+0x1d6>
 80088d0:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 80088d4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80088d8:	f240 80db 	bls.w	8008a92 <ACIM_VF_Controller+0x1d6>
 80088dc:	b510      	push	{r4, lr}
 80088de:	69c2      	ldr	r2, [r0, #28]
 80088e0:	ed2d 8b04 	vpush	{d8-d9}
 80088e4:	f002 43ff 	and.w	r3, r2, #2139095040	@ 0x7f800000
 80088e8:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80088ec:	b086      	sub	sp, #24
 80088ee:	4604      	mov	r4, r0
 80088f0:	f000 80ca 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 80088f4:	6a43      	ldr	r3, [r0, #36]	@ 0x24
 80088f6:	f003 41ff 	and.w	r1, r3, #2139095040	@ 0x7f800000
 80088fa:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 80088fe:	f000 80c3 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008902:	edd0 6a04 	vldr	s13, [r0, #16]
 8008906:	ee16 1a90 	vmov	r1, s13
 800890a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800890e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008912:	f000 80b9 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008916:	eef5 6ac0 	vcmpe.f32	s13, #0.0
 800891a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800891e:	f100 80b3 	bmi.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008922:	edd0 5a06 	vldr	s11, [r0, #24]
 8008926:	ee15 1a90 	vmov	r1, s11
 800892a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800892e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008932:	f000 80a9 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008936:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 800893a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800893e:	f100 80a3 	bmi.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008942:	ed90 6a05 	vldr	s12, [r0, #20]
 8008946:	ee16 1a10 	vmov	r1, s12
 800894a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800894e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008952:	f000 8099 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008956:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 800895a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800895e:	f100 8093 	bmi.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008962:	ed90 9a02 	vldr	s18, [r0, #8]
 8008966:	ee19 1a10 	vmov	r1, s18
 800896a:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800896e:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008972:	f000 8089 	beq.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008976:	eeb5 9ac0 	vcmpe.f32	s18, #0.0
 800897a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800897e:	f240 8083 	bls.w	8008a88 <ACIM_VF_Controller+0x1cc>
 8008982:	ee07 2a10 	vmov	s14, r2
 8008986:	eeb0 7ac7 	vabs.f32	s14, s14
 800898a:	eef4 5ac7 	vcmpe.f32	s11, s14
 800898e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008992:	d805      	bhi.n	80089a0 <ACIM_VF_Controller+0xe4>
 8008994:	ed9f 6a40 	vldr	s12, [pc, #256]	@ 8008a98 <ACIM_VF_Controller+0x1dc>
 8008998:	ee66 6a86 	vmul.f32	s13, s13, s12
 800899c:	ee26 6a87 	vmul.f32	s12, s13, s14
 80089a0:	eeb4 9ac6 	vcmpe.f32	s18, s12
 80089a4:	ed9f 7a3d 	vldr	s14, [pc, #244]	@ 8008a9c <ACIM_VF_Controller+0x1e0>
 80089a8:	ee06 3a90 	vmov	s13, r3
 80089ac:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089b0:	bf58      	it	pl
 80089b2:	eeb0 9a46 	vmovpl.f32	s18, s12
 80089b6:	ee26 8a87 	vmul.f32	s16, s13, s14
 80089ba:	eef4 7ac9 	vcmpe.f32	s15, s18
 80089be:	bf48      	it	mi
 80089c0:	eeb0 6a49 	vmovmi.f32	s12, s18
 80089c4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089c8:	bf54      	ite	pl
 80089ca:	ed84 6a03 	vstrpl	s12, [r4, #12]
 80089ce:	edc4 7a03 	vstrmi	s15, [r4, #12]
 80089d2:	eeb0 0a48 	vmov.f32	s0, s16
 80089d6:	bf48      	it	mi
 80089d8:	eeb0 9a67 	vmovmi.f32	s18, s15
 80089dc:	f7fa ff7e 	bl	80038dc <MCM_floatTrig_Functions>
 80089e0:	eddf 7a2f 	vldr	s15, [pc, #188]	@ 8008aa0 <ACIM_VF_Controller+0x1e4>
 80089e4:	edd4 9a03 	vldr	s19, [r4, #12]
 80089e8:	eef0 8a40 	vmov.f32	s17, s0
 80089ec:	ee38 0a27 	vadd.f32	s0, s16, s15
 80089f0:	f7fa ff74 	bl	80038dc <MCM_floatTrig_Functions>
 80089f4:	eddf 7a2b 	vldr	s15, [pc, #172]	@ 8008aa4 <ACIM_VF_Controller+0x1e8>
 80089f8:	ee69 9a80 	vmul.f32	s19, s19, s0
 80089fc:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008a00:	ed94 8a03 	vldr	s16, [r4, #12]
 8008a04:	f7fa ff6a 	bl	80038dc <MCM_floatTrig_Functions>
 8008a08:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 8008a0c:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 8008a10:	eec6 5a27 	vdiv.f32	s11, s12, s15
 8008a14:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 8008a18:	ee65 7aa8 	vmul.f32	s15, s11, s17
 8008a1c:	ee65 6aa9 	vmul.f32	s13, s11, s19
 8008a20:	ee67 7a89 	vmul.f32	s15, s15, s18
 8008a24:	ee28 7a00 	vmul.f32	s14, s16, s0
 8008a28:	eef4 7ac6 	vcmpe.f32	s15, s12
 8008a2c:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a30:	bfdc      	itt	le
 8008a32:	ee77 7a86 	vaddle.f32	s15, s15, s12
 8008a36:	eeb6 0a00 	vmovle.f32	s0, #96	@ 0x3f000000  0.5
 8008a3a:	eef4 6ae0 	vcmpe.f32	s13, s1
 8008a3e:	bfd4      	ite	le
 8008a40:	ee27 0a80 	vmulle.f32	s0, s15, s0
 8008a44:	eeb0 0a46 	vmovgt.f32	s0, s12
 8008a48:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a4c:	ee27 7a25 	vmul.f32	s14, s14, s11
 8008a50:	dc05      	bgt.n	8008a5e <ACIM_VF_Controller+0x1a2>
 8008a52:	ee76 6aa0 	vadd.f32	s13, s13, s1
 8008a56:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 8008a5a:	ee66 0aa0 	vmul.f32	s1, s13, s1
 8008a5e:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 8008a62:	eeb4 7ac1 	vcmpe.f32	s14, s2
 8008a66:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a6a:	dc05      	bgt.n	8008a78 <ACIM_VF_Controller+0x1bc>
 8008a6c:	ee37 7a01 	vadd.f32	s14, s14, s2
 8008a70:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 8008a74:	ee27 1a01 	vmul.f32	s2, s14, s2
 8008a78:	6860      	ldr	r0, [r4, #4]
 8008a7a:	b006      	add	sp, #24
 8008a7c:	ecbd 8b04 	vpop	{d8-d9}
 8008a80:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 8008a84:	f000 ba6c 	b.w	8008f60 <PWM_SetPhasePWMOutputs>
 8008a88:	2080      	movs	r0, #128	@ 0x80
 8008a8a:	b006      	add	sp, #24
 8008a8c:	ecbd 8b04 	vpop	{d8-d9}
 8008a90:	bd10      	pop	{r4, pc}
 8008a92:	2080      	movs	r0, #128	@ 0x80
 8008a94:	4770      	bx	lr
 8008a96:	bf00      	nop
 8008a98:	40c90fdb 	.word	0x40c90fdb
 8008a9c:	42652ee0 	.word	0x42652ee0
 8008aa0:	43700000 	.word	0x43700000
 8008aa4:	42f00000 	.word	0x42f00000
