
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r3\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

080088b4 <ACIM_VF_Controller>:
 80088b4:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 80088b8:	ee17 3a90 	vmov	r3, s15
 80088bc:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 80088c0:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80088c4:	f000 80e1 	beq.w	8008a8a <ACIM_VF_Controller+0x1d6>
 80088c8:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 80088cc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80088d0:	f240 80db 	bls.w	8008a8a <ACIM_VF_Controller+0x1d6>
 80088d4:	b510      	push	{r4, lr}
 80088d6:	69c2      	ldr	r2, [r0, #28]
 80088d8:	ed2d 8b04 	vpush	{d8-d9}
 80088dc:	f002 43ff 	and.w	r3, r2, #2139095040	@ 0x7f800000
 80088e0:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 80088e4:	b086      	sub	sp, #24
 80088e6:	4604      	mov	r4, r0
 80088e8:	f000 80ca 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 80088ec:	6a43      	ldr	r3, [r0, #36]	@ 0x24
 80088ee:	f003 41ff 	and.w	r1, r3, #2139095040	@ 0x7f800000
 80088f2:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 80088f6:	f000 80c3 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 80088fa:	edd0 6a04 	vldr	s13, [r0, #16]
 80088fe:	ee16 1a90 	vmov	r1, s13
 8008902:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008906:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800890a:	f000 80b9 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800890e:	eef5 6ac0 	vcmpe.f32	s13, #0.0
 8008912:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008916:	f100 80b3 	bmi.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800891a:	edd0 5a06 	vldr	s11, [r0, #24]
 800891e:	ee15 1a90 	vmov	r1, s11
 8008922:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008926:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800892a:	f000 80a9 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800892e:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 8008932:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008936:	f100 80a3 	bmi.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800893a:	ed90 6a05 	vldr	s12, [r0, #20]
 800893e:	ee16 1a10 	vmov	r1, s12
 8008942:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008946:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800894a:	f000 8099 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800894e:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 8008952:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008956:	f100 8093 	bmi.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800895a:	ed90 9a02 	vldr	s18, [r0, #8]
 800895e:	ee19 1a10 	vmov	r1, s18
 8008962:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008966:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800896a:	f000 8089 	beq.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800896e:	eeb5 9ac0 	vcmpe.f32	s18, #0.0
 8008972:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008976:	f240 8083 	bls.w	8008a80 <ACIM_VF_Controller+0x1cc>
 800897a:	ee07 2a10 	vmov	s14, r2
 800897e:	eeb0 7ac7 	vabs.f32	s14, s14
 8008982:	eef4 5ac7 	vcmpe.f32	s11, s14
 8008986:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800898a:	d805      	bhi.n	8008998 <ACIM_VF_Controller+0xe4>
 800898c:	ed9f 6a40 	vldr	s12, [pc, #256]	@ 8008a90 <ACIM_VF_Controller+0x1dc>
 8008990:	ee66 6a86 	vmul.f32	s13, s13, s12
 8008994:	ee26 6a87 	vmul.f32	s12, s13, s14
 8008998:	eeb4 9ac6 	vcmpe.f32	s18, s12
 800899c:	ed9f 7a3d 	vldr	s14, [pc, #244]	@ 8008a94 <ACIM_VF_Controller+0x1e0>
 80089a0:	ee06 3a90 	vmov	s13, r3
 80089a4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089a8:	bf58      	it	pl
 80089aa:	eeb0 9a46 	vmovpl.f32	s18, s12
 80089ae:	ee26 8a87 	vmul.f32	s16, s13, s14
 80089b2:	eef4 7ac9 	vcmpe.f32	s15, s18
 80089b6:	bf48      	it	mi
 80089b8:	eeb0 6a49 	vmovmi.f32	s12, s18
 80089bc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089c0:	bf54      	ite	pl
 80089c2:	ed84 6a03 	vstrpl	s12, [r4, #12]
 80089c6:	edc4 7a03 	vstrmi	s15, [r4, #12]
 80089ca:	eeb0 0a48 	vmov.f32	s0, s16
 80089ce:	bf48      	it	mi
 80089d0:	eeb0 9a67 	vmovmi.f32	s18, s15
 80089d4:	f7fa ff82 	bl	80038dc <MCM_floatTrig_Functions>
 80089d8:	eddf 7a2f 	vldr	s15, [pc, #188]	@ 8008a98 <ACIM_VF_Controller+0x1e4>
 80089dc:	edd4 9a03 	vldr	s19, [r4, #12]
 80089e0:	eef0 8a40 	vmov.f32	s17, s0
 80089e4:	ee38 0a27 	vadd.f32	s0, s16, s15
 80089e8:	f7fa ff78 	bl	80038dc <MCM_floatTrig_Functions>
 80089ec:	eddf 7a2b 	vldr	s15, [pc, #172]	@ 8008a9c <ACIM_VF_Controller+0x1e8>
 80089f0:	ee69 9a80 	vmul.f32	s19, s19, s0
 80089f4:	ee38 0a27 	vadd.f32	s0, s16, s15
 80089f8:	ed94 8a03 	vldr	s16, [r4, #12]
 80089fc:	f7fa ff6e 	bl	80038dc <MCM_floatTrig_Functions>
 8008a00:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 8008a04:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 8008a08:	eec6 5a27 	vdiv.f32	s11, s12, s15
 8008a0c:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 8008a10:	ee65 7aa8 	vmul.f32	s15, s11, s17
 8008a14:	ee65 6aa9 	vmul.f32	s13, s11, s19
 8008a18:	ee67 7a89 	vmul.f32	s15, s15, s18
 8008a1c:	ee28 7a00 	vmul.f32	s14, s16, s0
 8008a20:	eef4 7ac6 	vcmpe.f32	s15, s12
 8008a24:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a28:	bfdc      	itt	le
 8008a2a:	ee77 7a86 	vaddle.f32	s15, s15, s12
 8008a2e:	eeb6 0a00 	vmovle.f32	s0, #96	@ 0x3f000000  0.5
 8008a32:	eef4 6ae0 	vcmpe.f32	s13, s1
 8008a36:	bfd4      	ite	le
 8008a38:	ee27 0a80 	vmulle.f32	s0, s15, s0
 8008a3c:	eeb0 0a46 	vmovgt.f32	s0, s12
 8008a40:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a44:	ee27 7a25 	vmul.f32	s14, s14, s11
 8008a48:	dc05      	bgt.n	8008a56 <ACIM_VF_Controller+0x1a2>
 8008a4a:	ee76 6aa0 	vadd.f32	s13, s13, s1
 8008a4e:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 8008a52:	ee66 0aa0 	vmul.f32	s1, s13, s1
 8008a56:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 8008a5a:	eeb4 7ac1 	vcmpe.f32	s14, s2
 8008a5e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a62:	dc05      	bgt.n	8008a70 <ACIM_VF_Controller+0x1bc>
 8008a64:	ee37 7a01 	vadd.f32	s14, s14, s2
 8008a68:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 8008a6c:	ee27 1a01 	vmul.f32	s2, s14, s2
 8008a70:	6860      	ldr	r0, [r4, #4]
 8008a72:	b006      	add	sp, #24
 8008a74:	ecbd 8b04 	vpop	{d8-d9}
 8008a78:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 8008a7c:	f000 ba6c 	b.w	8008f58 <PWM_SetPhasePWMOutputs>
 8008a80:	2080      	movs	r0, #128	@ 0x80
 8008a82:	b006      	add	sp, #24
 8008a84:	ecbd 8b04 	vpop	{d8-d9}
 8008a88:	bd10      	pop	{r4, pc}
 8008a8a:	2080      	movs	r0, #128	@ 0x80
 8008a8c:	4770      	bx	lr
 8008a8e:	bf00      	nop
 8008a90:	40c90fdb 	.word	0x40c90fdb
 8008a94:	42652ee0 	.word	0x42652ee0
 8008a98:	43700000 	.word	0x43700000
 8008a9c:	42f00000 	.word	0x42f00000
