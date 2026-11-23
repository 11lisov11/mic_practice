
C:\mic_practice\artifacts\live_bench_20261024\vf_smooth_start_r1\build\nucleo\ACIM-NUCLEOG431RB-IPM15B-VF_OL.elf:     file format elf32-littlearm


Disassembly of section .text:

0800ba54 <ACIM_VF_Controller>:
 800ba54:	edd0 7a14 	vldr	s15, [r0, #80]	@ 0x50
 800ba58:	ee17 3a90 	vmov	r3, s15
 800ba5c:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 800ba60:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 800ba64:	f000 811e 	beq.w	800bca4 <ACIM_VF_Controller+0x250>
 800ba68:	eef5 7ac0 	vcmpe.f32	s15, #0.0
 800ba6c:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800ba70:	f240 8118 	bls.w	800bca4 <ACIM_VF_Controller+0x250>
 800ba74:	b510      	push	{r4, lr}
 800ba76:	69c3      	ldr	r3, [r0, #28]
 800ba78:	ed2d 8b04 	vpush	{d8-d9}
 800ba7c:	f003 42ff 	and.w	r2, r3, #2139095040	@ 0x7f800000
 800ba80:	f1b2 4fff 	cmp.w	r2, #2139095040	@ 0x7f800000
 800ba84:	b086      	sub	sp, #24
 800ba86:	4604      	mov	r4, r0
 800ba88:	f000 8090 	beq.w	800bbac <ACIM_VF_Controller+0x158>
 800ba8c:	6a42      	ldr	r2, [r0, #36]	@ 0x24
 800ba8e:	f002 41ff 	and.w	r1, r2, #2139095040	@ 0x7f800000
 800ba92:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800ba96:	f000 8089 	beq.w	800bbac <ACIM_VF_Controller+0x158>
 800ba9a:	ed90 7a04 	vldr	s14, [r0, #16]
 800ba9e:	ee17 1a10 	vmov	r1, s14
 800baa2:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800baa6:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800baaa:	d07f      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800baac:	eeb5 7ac0 	vcmpe.f32	s14, #0.0
 800bab0:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bab4:	d47a      	bmi.n	800bbac <ACIM_VF_Controller+0x158>
 800bab6:	ed90 6a06 	vldr	s12, [r0, #24]
 800baba:	ee16 1a10 	vmov	r1, s12
 800babe:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800bac2:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800bac6:	d071      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bac8:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 800bacc:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bad0:	d46c      	bmi.n	800bbac <ACIM_VF_Controller+0x158>
 800bad2:	ed90 5a05 	vldr	s10, [r0, #20]
 800bad6:	ee15 1a10 	vmov	r1, s10
 800bada:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800bade:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800bae2:	d063      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bae4:	eeb5 5ac0 	vcmpe.f32	s10, #0.0
 800bae8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800baec:	d45e      	bmi.n	800bbac <ACIM_VF_Controller+0x158>
 800baee:	edd0 4a02 	vldr	s9, [r0, #8]
 800baf2:	ee14 1a90 	vmov	r1, s9
 800baf6:	f001 41ff 	and.w	r1, r1, #2139095040	@ 0x7f800000
 800bafa:	f1b1 4fff 	cmp.w	r1, #2139095040	@ 0x7f800000
 800bafe:	d055      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bb00:	eef5 4ac0 	vcmpe.f32	s9, #0.0
 800bb04:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bb08:	d950      	bls.n	800bbac <ACIM_VF_Controller+0x158>
 800bb0a:	ed9f 4a67 	vldr	s8, [pc, #412]	@ 800bca8 <ACIM_VF_Controller+0x254>
 800bb0e:	ee06 3a90 	vmov	s13, r3
 800bb12:	ee67 5a04 	vmul.f32	s11, s14, s8
 800bb16:	eef0 6ae6 	vabs.f32	s13, s13
 800bb1a:	ee65 5aa6 	vmul.f32	s11, s11, s13
 800bb1e:	eeb5 6ac0 	vcmpe.f32	s12, #0.0
 800bb22:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bb26:	edc0 5a03 	vstr	s11, [r0, #12]
 800bb2a:	dd44      	ble.n	800bbb6 <ACIM_VF_Controller+0x162>
 800bb2c:	eeb4 6ae6 	vcmpe.f32	s12, s13
 800bb30:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bb34:	dd3f      	ble.n	800bbb6 <ACIM_VF_Controller+0x162>
 800bb36:	ee27 7a06 	vmul.f32	s14, s14, s12
 800bb3a:	eef6 3a00 	vmov.f32	s7, #96	@ 0x3f000000  0.5
 800bb3e:	ee27 7a04 	vmul.f32	s14, s14, s8
 800bb42:	eea7 5a63 	vfms.f32	s10, s14, s7
 800bb46:	eeb5 5ac0 	vcmpe.f32	s10, #0.0
 800bb4a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bb4e:	dd32      	ble.n	800bbb6 <ACIM_VF_Controller+0x162>
 800bb50:	ee17 3a10 	vmov	r3, s14
 800bb54:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 800bb58:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 800bb5c:	d026      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bb5e:	eeb5 4a08 	vmov.f32	s8, #88	@ 0x3ec00000  0.375
 800bb62:	ee27 7a04 	vmul.f32	s14, s14, s8
 800bb66:	eeb4 7ac5 	vcmpe.f32	s14, s10
 800bb6a:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bb6e:	d41d      	bmi.n	800bbac <ACIM_VF_Controller+0x158>
 800bb70:	ee86 7a86 	vdiv.f32	s14, s13, s12
 800bb74:	eef7 6a00 	vmov.f32	s13, #112	@ 0x3f800000  1.0
 800bb78:	eeb2 6a00 	vmov.f32	s12, #32	@ 0x41000000  8.0
 800bb7c:	ee76 6ac7 	vsub.f32	s13, s13, s14
 800bb80:	ee27 7a06 	vmul.f32	s14, s14, s12
 800bb84:	ee27 7a26 	vmul.f32	s14, s14, s13
 800bb88:	ee27 7a26 	vmul.f32	s14, s14, s13
 800bb8c:	eee7 5a05 	vfma.f32	s11, s14, s10
 800bb90:	ee15 3a90 	vmov	r3, s11
 800bb94:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 800bb98:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 800bb9c:	edc0 5a03 	vstr	s11, [r0, #12]
 800bba0:	d004      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bba2:	eef5 5ac0 	vcmpe.f32	s11, #0.0
 800bba6:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bbaa:	d50b      	bpl.n	800bbc4 <ACIM_VF_Controller+0x170>
 800bbac:	2080      	movs	r0, #128	@ 0x80
 800bbae:	b006      	add	sp, #24
 800bbb0:	ecbd 8b04 	vpop	{d8-d9}
 800bbb4:	bd10      	pop	{r4, pc}
 800bbb6:	ee15 3a90 	vmov	r3, s11
 800bbba:	f003 43ff 	and.w	r3, r3, #2139095040	@ 0x7f800000
 800bbbe:	f1b3 4fff 	cmp.w	r3, #2139095040	@ 0x7f800000
 800bbc2:	d0f3      	beq.n	800bbac <ACIM_VF_Controller+0x158>
 800bbc4:	eef4 4ae7 	vcmpe.f32	s9, s15
 800bbc8:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bbcc:	bfb8      	it	lt
 800bbce:	eef0 7a64 	vmovlt.f32	s15, s9
 800bbd2:	ed9f 7a36 	vldr	s14, [pc, #216]	@ 800bcac <ACIM_VF_Controller+0x258>
 800bbd6:	ee06 2a90 	vmov	s13, r2
 800bbda:	eef4 5ae7 	vcmpe.f32	s11, s15
 800bbde:	ee66 8a87 	vmul.f32	s17, s13, s14
 800bbe2:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bbe6:	bfb4      	ite	lt
 800bbe8:	eeb0 8a65 	vmovlt.f32	s16, s11
 800bbec:	eeb0 8a67 	vmovge.f32	s16, s15
 800bbf0:	eeb0 0a68 	vmov.f32	s0, s17
 800bbf4:	ed84 8a03 	vstr	s16, [r4, #12]
 800bbf8:	f7fa ff5e 	bl	8006ab8 <MCM_floatTrig_Functions>
 800bbfc:	eddf 7a2c 	vldr	s15, [pc, #176]	@ 800bcb0 <ACIM_VF_Controller+0x25c>
 800bc00:	edd4 9a03 	vldr	s19, [r4, #12]
 800bc04:	eeb0 9a40 	vmov.f32	s18, s0
 800bc08:	ee38 0aa7 	vadd.f32	s0, s17, s15
 800bc0c:	f7fa ff54 	bl	8006ab8 <MCM_floatTrig_Functions>
 800bc10:	eddf 7a28 	vldr	s15, [pc, #160]	@ 800bcb4 <ACIM_VF_Controller+0x260>
 800bc14:	ee69 9a80 	vmul.f32	s19, s19, s0
 800bc18:	ee38 0aa7 	vadd.f32	s0, s17, s15
 800bc1c:	edd4 8a03 	vldr	s17, [r4, #12]
 800bc20:	f7fa ff4a 	bl	8006ab8 <MCM_floatTrig_Functions>
 800bc24:	edd4 7a14 	vldr	s15, [r4, #80]	@ 0x50
 800bc28:	eeb7 6a00 	vmov.f32	s12, #112	@ 0x3f800000  1.0
 800bc2c:	eec6 5a27 	vdiv.f32	s11, s12, s15
 800bc30:	eef7 0a00 	vmov.f32	s1, #112	@ 0x3f800000  1.0
 800bc34:	ee69 7a25 	vmul.f32	s15, s18, s11
 800bc38:	ee69 6aa5 	vmul.f32	s13, s19, s11
 800bc3c:	ee67 7a88 	vmul.f32	s15, s15, s16
 800bc40:	ee28 7a80 	vmul.f32	s14, s17, s0
 800bc44:	eef4 7ac6 	vcmpe.f32	s15, s12
 800bc48:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bc4c:	bfd8      	it	le
 800bc4e:	ee77 7a86 	vaddle.f32	s15, s15, s12
 800bc52:	eef4 6ae0 	vcmpe.f32	s13, s1
 800bc56:	bfda      	itte	le
 800bc58:	eeb6 6a00 	vmovle.f32	s12, #96	@ 0x3f000000  0.5
 800bc5c:	ee27 0a86 	vmulle.f32	s0, s15, s12
 800bc60:	eeb0 0a46 	vmovgt.f32	s0, s12
 800bc64:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bc68:	ee27 7a25 	vmul.f32	s14, s14, s11
 800bc6c:	dc05      	bgt.n	800bc7a <ACIM_VF_Controller+0x226>
 800bc6e:	ee76 6aa0 	vadd.f32	s13, s13, s1
 800bc72:	eef6 0a00 	vmov.f32	s1, #96	@ 0x3f000000  0.5
 800bc76:	ee66 0aa0 	vmul.f32	s1, s13, s1
 800bc7a:	eeb7 1a00 	vmov.f32	s2, #112	@ 0x3f800000  1.0
 800bc7e:	eeb4 7ac1 	vcmpe.f32	s14, s2
 800bc82:	eef1 fa10 	vmrs	APSR_nzcv, fpscr
 800bc86:	dc05      	bgt.n	800bc94 <ACIM_VF_Controller+0x240>
 800bc88:	ee37 7a01 	vadd.f32	s14, s14, s2
 800bc8c:	eeb6 1a00 	vmov.f32	s2, #96	@ 0x3f000000  0.5
 800bc90:	ee27 1a01 	vmul.f32	s2, s14, s2
 800bc94:	6860      	ldr	r0, [r4, #4]
 800bc96:	b006      	add	sp, #24
 800bc98:	ecbd 8b04 	vpop	{d8-d9}
 800bc9c:	e8bd 4010 	ldmia.w	sp!, {r4, lr}
 800bca0:	f000 ba66 	b.w	800c170 <PWM_SetPhasePWMOutputs>
 800bca4:	2080      	movs	r0, #128	@ 0x80
 800bca6:	4770      	bx	lr
 800bca8:	40c90fdb 	.word	0x40c90fdb
 800bcac:	42652ee0 	.word	0x42652ee0
 800bcb0:	43700000 	.word	0x43700000
 800bcb4:	42f00000 	.word	0x42f00000
