"""Resolve saved thread stacks/mutex owners against exact ELF mappings; offline."""
import json,struct,bisect
from elftools.elf.elffile import ELFFile
from inspect_unoq_idle_RAM import ROOT,OUT,KERNEL,APP,RAM,u,symbols

def main():
    layout=json.loads((OUT/'ELF_layout.json').read_text());ext=layout['extensions'][0]
    with KERNEL.open('rb') as k,APP.open('rb') as a:
        kernel=ELFFile(k);app=ELFFile(a);ks=symbols(kernel);aps=symbols(app)
        bases={'.text':int(ext['mem'][0],16),'.data':int(ext['mem'][1],16),
            '.rodata':int(ext['mem'][2],16),'.bss':int(ext['mem'][3],16),
            '.llext.rodata.noreloc':int(ext['mem'][11],16)}
        mapped={}
        funcs=[]
        for scope,elf,syms in (('kernel',kernel,ks),('app',app,aps)):
            for name,s in syms.items():
                idx=s['st_shndx']
                if not isinstance(idx,int):continue
                section=elf.get_section(idx).name
                addr=s['st_value']
                if scope=='app':
                    if section not in bases:continue
                    addr=bases[section]+addr
                mapped[(scope,name)]=(addr,s['st_size'])
                if s['st_info']['type']=='STT_FUNC':funcs.append((addr&~1,s['st_size'],name,scope))
        funcs.sort()
        def resolve(addr):
            addr&=~1
            for start,size,name,scope in reversed(funcs):
                if start<=addr and addr<start+size:return f'{scope}:{name}+0x{addr-start:x}'
            return None
        bridge=mapped[('app','Bridge')][0]
        mutexes={}
        for name,addr in [('control',mapped[('app','_ZL15g_control_mutex')][0])]+[(name,bridge+offset) for name,offset in [('read',16),('write',36),('bridge',56),('outgoing',76)]]:
            mutexes[name]=dict(address=hex(addr),wait_next=hex(u(addr)),wait_prev=hex(u(addr+4)),owner=hex(u(addr+8)),count=u(addr+12),owner_prio=u(addr+16))
        stacks=[]
        for t in layout['threads']:
            psp=int(t['psp'],16);end=int(t['stack_start'],16)+t['stack_size']
            matches=[]
            for address in range(psp,end,4):
                value=u(address);name=resolve(value)
                if name:matches.append(dict(at=hex(address),value=hex(value),symbol=name))
            stacks.append(dict(thread=t['name'] or t['address'],state=t['state'],pended_on=t['pended_on'],matches=matches))
        values={}
        for name in ('mic_rpc_health','_ZL12g_rpc_routes','_ZL11g_timed_run'):
            addr,size=mapped[('app',name)];values[name]=dict(address=hex(addr),words=[u(addr+i) for i in range(0,size,4)])
        client=u(bridge);server=u(bridge+4);decoder=u(client)
        decoder_meta=dict(address=hex(decoder),client=hex(client),server=hex(server),
            server_decoder=hex(u(server)),transport=hex(u(decoder)),
            bytes_stored=u(decoder+1028),packet_type=u(decoder+1032),packet_size=u(decoder+1036),
            response_offset=u(decoder+1040),response_size=u(decoder+1044),msg_id=u(decoder+1048),discarded=u(decoder+1052))
        raw=RAM[decoder+4-0x20000000:decoder+1028-0x20000000]
        (OUT/'RPC_decoder_buffer.bin').write_bytes(raw)
        try:
            import msgpack
            unpack=msgpack.Unpacker(raw=False,strict_map_key=False);unpack.feed(raw[:decoder_meta['bytes_stored']])
            decoder_meta['decoded_objects']=list(unpack)
        except Exception as e:decoder_meta['parse_error']=str(e)
        serials={}
        for name in ('Serial1','Serial2','Serial3'):
            addr,size=mapped[('app',name)]
            serials[name]=dict(address=hex(addr),uart_device=hex(u(addr+16)),
                tx_ring=[u(addr+20+2*i,2) for i in range(10)],
                rx_ring=[u(addr+128+2*i,2) for i in range(10)],
                tx_sem=[hex(u(addr+104+4*i)) for i in range(5)],
                rx_sem=[hex(u(addr+212+4*i)) for i in range(5)])
        report=dict(mutexes=mutexes,stacks=stacks,values=values,decoder=decoder_meta,
            bridge_serial=hex(u(bridge+8)),serials=serials)
        (OUT/'waits_decoded.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))
if __name__=='__main__':main()
