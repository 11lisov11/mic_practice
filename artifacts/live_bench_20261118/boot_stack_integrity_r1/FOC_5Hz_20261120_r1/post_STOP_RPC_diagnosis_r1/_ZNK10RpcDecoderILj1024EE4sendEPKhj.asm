
C:\mic_practice\artifacts\live_bench_20261118\boot_stack_integrity_r1\build\uno\UNOQ_MOTOR.ino.elf:     file format elf32-littlearm


Disassembly of section .text:

0000cfa0 <_ZNK10RpcDecoderILj1024EE4sendEPKhj>:
    cfa0:	e92d 4ff8 	stmdb	sp!, {r3, r4, r5, r6, r7, r8, r9, sl, fp, lr}
    cfa4:	f8df 9058 	ldr.w	r9, [pc, #88]	@ d000 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x60>
    cfa8:	4607      	mov	r7, r0
    cfaa:	4688      	mov	r8, r1
    cfac:	4615      	mov	r5, r2
    cfae:	47c8      	blx	r9
    cfb0:	2400      	movs	r4, #0
    cfb2:	4606      	mov	r6, r0
    cfb4:	f8df a04c 	ldr.w	sl, [pc, #76]	@ d004 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x64>
    cfb8:	42ac      	cmp	r4, r5
    cfba:	d207      	bcs.n	cfcc <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x2c>
    cfbc:	47c8      	blx	r9
    cfbe:	1b80      	subs	r0, r0, r6
    cfc0:	f5b0 6ffa 	cmp.w	r0, #2000	@ 0x7d0
    cfc4:	d305      	bcc.n	cfd2 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x32>
    cfc6:	480c      	ldr	r0, [pc, #48]	@ (cff8 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x58>)
    cfc8:	4b0c      	ldr	r3, [pc, #48]	@ (cffc <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x5c>)
    cfca:	4798      	blx	r3
    cfcc:	4620      	mov	r0, r4
    cfce:	e8bd 8ff8 	ldmia.w	sp!, {r3, r4, r5, r6, r7, r8, r9, sl, fp, pc}
    cfd2:	6838      	ldr	r0, [r7, #0]
    cfd4:	eba5 0b04 	sub.w	fp, r5, r4
    cfd8:	6803      	ldr	r3, [r0, #0]
    cfda:	465a      	mov	r2, fp
    cfdc:	689b      	ldr	r3, [r3, #8]
    cfde:	eb08 0104 	add.w	r1, r8, r4
    cfe2:	4798      	blx	r3
    cfe4:	4583      	cmp	fp, r0
    cfe6:	d3f1      	bcc.n	cfcc <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x2c>
    cfe8:	4404      	add	r4, r0
    cfea:	2800      	cmp	r0, #0
    cfec:	d1e4      	bne.n	cfb8 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x18>
    cfee:	2100      	movs	r1, #0
    cff0:	200a      	movs	r0, #10
    cff2:	47d0      	blx	sl
    cff4:	e7e0      	b.n	cfb8 <_ZNK10RpcDecoderILj1024EE4sendEPKhj+0x18>
    cff6:	bf00      	nop
    cff8:	00000004 	.word	0x00000004
	...
