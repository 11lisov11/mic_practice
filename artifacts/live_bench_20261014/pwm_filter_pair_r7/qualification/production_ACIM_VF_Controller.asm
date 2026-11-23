
C:\mic_practice\artifacts\live_bench_20261014\pwm_filter_pair_r7\production\nucleo\STM32CubeIDE\Debug\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

080088f4 <ACIM_VF_Controller>:
 80088f4:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 80088f8:	ee17 3a90 	vmov	r3, s15
 80088fc:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 8008900:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 8008904:	f000 80e1 	beq.w	8008aca <ACIM_VF_Controller+0x1d6>
 8008908:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 800890c:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008910:	f240 80db 	bls.w	8008aca <ACIM_VF_Controller+0x1d6>
 8008914:	b510      	push	{r4, lr}
 8008916:	69c2      	ldr	r2, [r0, #28]
 8008918:	ed2d 8b04 	vpush	{d8-d9}
 800891c:	f002 43ff 	and.w	r3, r2, #2139095040	@ 0x7f800000
 8008920:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 8008924:	b086      	sub	sp, #24
 8008926:	4604      	mov	r4, r0
 8008928:	f000 80ca 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800892c:	6a43      	ldr	r3, [r0, #36]	@ 0x24
 800892e:	f003 41ff 	and.w	r1, r3, #2139095040	@ 0x7f800000
 8008932:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 8008936:	f000 80c3 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800893a:	edd0 6a04 	vldr	s13, [r0, #16]
 800893e:	ee16 1a90 	vmov	r1, s13
 8008942:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008946:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800894a:	f000 80b9 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800894e:	eef5 6ac0 	vcmpe.f32	s13, #0.0
 8008952:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008956:	f100 80b3 	bmi.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800895a:	edd0 5a06 	vldr	s11, [r0, #24]
 800895e:	ee15 1a90 	vmov	r1, s11
 8008962:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008966:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800896a:	f000 80a9 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800896e:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 8008972:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008976:	f100 80a3 	bmi.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800897a:	ed90 6a05 	vldr	s12, [r0, #20]
 800897e:	ee16 1a10 	vmov	r1, s12
 8008982:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 8008986:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800898a:	f000 8099 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800898e:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 8008992:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008996:	f100 8093 	bmi.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 800899a:	ed90 9a02 	vldr	s18, [r0, #8]
 800899e:	ee19 1a10 	vmov	r1, s18
 80089a2:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 80089a6:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 80089aa:	f000 8089 	beq.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 80089ae:	eeb5 9ac0 	vcmpe.f32	s18, #0.0
 80089b2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089b6:	f240 8083 	bls.w	8008ac0 <ACIM_VF_Controller+0x1cc>
 80089ba:	ee07 2a10 	vmov	s14, r2
 80089be:	eeb0 7ac7 	vabs.f32	s14, s14
 80089c2:	eef4 5ac7 	vcmpe.f32	s11, s14
 80089c6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089ca:	d805      	bhi.n	80089d8 <ACIM_VF_Controller+0xe4>
 80089cc:	ed9f 6a40 	vldr	s12, [pc, #256]	@ 8008ad0 <ACIM_VF_Controller+0x1dc>
 80089d0:	ee66 6a86 	vmul.f32	s13, s13, s12
 80089d4:	ee26 6a87 	vmul.f32	s12, s13, s14
 80089d8:	eeb4 9ac6 	vcmpe.f32	s18, s12
 80089dc:	ed9f 7a3d 	vldr	s14, [pc, #244]	@ 8008ad4 <ACIM_VF_Controller+0x1e0>
 80089e0:	ee06 3a90 	vmov	s13, r3
 80089e4:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 80089e8:	bf58      	it	pl
 80089ea:	eeb0 9a46 	vmovpl.f32	s18, s12
 80089ee:	ee26 8a87 	vmul.f32	s16, s13, s14
 80089f2:	eef4 7ac9 	vcmpe.f32	s15, s18
 80089f6:	bf48      	it	mi
 80089f8:	eeb0 6a49 	vmovmi.f32	s12, s18
 80089fc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a00:	bf54      	ite	pl
 8008a02:	ed84 6a03 	vstrpl	s12, [r4, #12]
 8008a06:	edc4 7a03 	vstrmi	s15, [r4, #12]
 8008a0a:	eeb0 0a48 	vmov.f32	s0, s16
 8008a0e:	bf48      	it	mi
 8008a10:	eeb0 9a67 	vmovmi.f32	s18, s15
 8008a14:	f7fa ff7e 	bl	8003914 <MCM_floatTrig_Functions>
 8008a18:	eddf 7a2f 	vldr	s15, [pc, #188]	@ 8008ad8 <ACIM_VF_Controller+0x1e4>
 8008a1c:	edd4 9a03 	vldr	s19, [r4, #12]
 8008a20:	eef0 8a40 	vmov.f32	s17, s0
 8008a24:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008a28:	f7fa ff74 	bl	8003914 <MCM_floatTrig_Functions>
 8008a2c:	eddf 7a2b 	vldr	s15, [pc, #172]	@ 8008adc <ACIM_VF_Controller+0x1e8>
 8008a30:	ee69 9a80 	vmul.f32	s19, s19, s0
 8008a34:	ee38 0a27 	vadd.f32	s0, s16, s15
 8008a38:	ed94 8a03 	vldr	s16, [r4, #12]
 8008a3c:	f7fa ff6a 	bl	8003914 <MCM_floatTrig_Functions>
 8008a40:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 8008a44:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 8008a48:	eec6 5a27 	vdiv.f32	s11, s12, s15
 8008a4c:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 8008a50:	ee65 7aa8 	vmul.f32	s15, s11, s17
 8008a54:	ee65 6aa9 	vmul.f32	s13, s11, s19
 8008a58:	ee67 7a89 	vmul.f32	s15, s15, s18
 8008a5c:	ee28 7a00 	vmul.f32	s14, s16, s0
 8008a60:	eef4 7ac6 	vcmpe.f32	s15, s12
 8008a64:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a68:	bfdc      	itt	le
 8008a6a:	ee77 7a86 	vaddle.f32	s15, s15, s12
 8008a6e:	eeb6 0a00 	vmovle.f32	s0, #96	@ 0x3f000000  0.5
 8008a72:	eef4 6ae0 	vcmpe.f32	s13, s1
 8008a76:	bfd4      	ite	le
 8008a78:	ee27 0a80 	vmulle.f32	s0, s15, s0
 8008a7c:	eeb0 0a46 	vmovgt.f32	s0, s12
 8008a80:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008a84:	ee27 7a25 	vmul.f32	s14, s14, s11
 8008a88:	dc05      	bgt.n	8008a96 <ACIM_VF_Controller+0x1a2>
 8008a8a:	ee76 6aa0 	vadd.f32	s13, s13, s1
 8008a8e:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 8008a92:	ee66 0aa0 	vmul.f32	s1, s13, s1
 8008a96:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 8008a9a:	eeb4 7ac1 	vcmpe.f32	s14, s2
 8008a9e:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 8008aa2:	dc05      	bgt.n	8008ab0 <ACIM_VF_Controller+0x1bc>
 8008aa4:	ee37 7a01 	vadd.f32	s14, s14, s2
 8008aa8:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 8008aac:	ee27 1a01 	vmul.f32	s2, s14, s2
 8008ab0:	6860      	ldr	r0, [r4, #4]
 8008ab2:	b006      	add	sp, #24
 8008ab4:	ecbd 8b04 	vpop	{d8-d9}
 8008ab8:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 8008abc:	f000 ba6c 	b.w	8008f98 <PWM_SetPhasePWMOutputs>
 8008ac0:	2080      	movs	r0, #128	@ 0x80
 8008ac2:	b006      	add	sp, #24
 8008ac4:	ecbd 8b04 	vpop	{d8-d9}
 8008ac8:	bd10      	pop	{r4, pc}
 8008aca:	2080      	movs	r0, #128	@ 0x80
 8008acc:	4770      	bx	lr
 8008ace:	bf00      	nop
 8008ad0:	40c90fdb 	.word	0x40c90fdb
 8008ad4:	42652ee0 	.word	0x42652ee0
 8008ad8:	43700000 	.word	0x43700000
 8008adc:	42f00000 	.word	0x42f00000
