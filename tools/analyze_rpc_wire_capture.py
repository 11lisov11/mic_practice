"""Offline UART/RPC accounting. Preserve the raw harness verdict and captures."""
import json, struct, sys
from pathlib import Path
import msgpack


def packets(path):
    raw=path.read_bytes();good=[];invalid=[];position=0;bad_start=None
    # A reconnect can start in the middle of the old reply. Search bounded RPC
    # headers rather than trusting a stray str32/array32 length in that suffix.
    while position<len(raw):
        b=raw[position:position+2]
        if len(b)==2 and b[0] in (0x93,0x94) and b[1] in (0,1,2):
            u=msgpack.Unpacker(raw=False,max_buffer_size=2**24,max_array_len=1024,max_str_len=2**20)
            u.feed(raw[position:])
            try:obj=next(u)
            except (ValueError,msgpack.OutOfData,msgpack.FormatError,msgpack.StackError,StopIteration):obj=None
            if isinstance(obj,list) and len(obj) in (3,4) and obj[0] in (0,1,2):
                if bad_start is not None:
                    invalid.append(dict(start=bad_start,end=position,object='Unframed/rejected byte range'));bad_start=None
                end=position+u.tell();good.append(dict(start=position,end=end,obj=obj));position=end;continue
        if bad_start is None:bad_start=position
        position+=1
    if bad_start is not None:invalid.append(dict(start=bad_start,end=len(raw),object='Unframed/rejected byte range'))
    return raw,good,invalid


def serial(path):
    b=path.read_bytes()
    def ring(offset,buffer):
        put=struct.unpack_from('<3H',b,offset+4);get=struct.unpack_from('<3H',b,offset+10)
        size=struct.unpack_from('<I',b,offset+16)[0];assert size==64
        n=(get[0]-get[2])&65535;assert n<=size
        data=b[buffer:buffer+size]
        return dict(put=put,get=get,pending=(put[1]-get[0])&65535,
                    last64_hex=(data[n:]+data[:n]).hex())
    return dict(tx=ring(20,40),rx=ring(128,148))


def main():
    folder=Path(sys.argv[1]);target=folder/'wire_analysis.json';assert not target.exists()
    m=json.loads((folder/'report.json').read_text())
    rx,received,invalid=packets(folder/'from_MCU.bin');tx,sent,bad_tx=packets(folder/'to_MCU.bin')
    first=received[0]['start'] if received else len(rx)
    later=[x for x in invalid if x['start']>=first]
    replies={x['obj'][1] for x in received if x['obj'][0]==1}
    gets=[x['obj'][1] for x in sent if x['obj'][0]==0 and x['obj'][2]=='get']
    report=dict(raw_harness_passed=m['passed'],GET_calls=m['GET'],GET_requests_on_wire=len(gets),
        unanswered_GET_ids=[x for x in gets if x not in replies],
        MCU_bytes=len(rx),Linux_bytes_logged=len(tx),startup_invalid_objects=len(invalid)-len(later),
        post_first_RPC_invalid_objects=later,Linux_invalid_objects=bad_tx,
        proxy_errors=m['proxy_errors'],harness_error=m.get('error'),
        post_handshake_transport_passed=not later and not bad_tx and not m['proxy_errors'] and not m.get('error'),
        START=0,CLEAR=0,MCU_reset=0,scope='GET-only transport test. Not motor qualification.')
    stop=folder/'investigator_stop.json'
    if stop.exists():report['investigator_stop']=json.loads(stop.read_text())
    for name in ('baseline','failure'):
        p=folder/('serial_'+name+'.bin')
        if p.exists():report[name+'_serial']=serial(p)
    if all(x+'_serial' in report and x+'_capture' in m for x in ('baseline','failure')):
        b=report['baseline_serial'];f=report['failure_serial'];bc=m['baseline_capture'];fc=m['failure_capture']
        # 16-bit ring indices wrap. Ranges include capture-time traffic.
        report['ring_wire_accounting']=dict(
            MCU_tx_delta_mod65536=(f['tx']['put'][1]-b['tx']['put'][1])&65535,
            Linux_rx_delta_range=[fc['wire_before']-bc['wire_after'],fc['wire_after']-bc['wire_before']],
            MCU_rx_delta_mod65536=(f['rx']['put'][1]-b['rx']['put'][1])&65535,
            Linux_tx_delta_range=[fc['physical_written_before']-bc['physical_written_after'],fc['physical_written_after']-bc['physical_written_before']],
            note='Indices are non-atomic passive samples. Compare modulo65536 and allow TX pending bytes.')
    target.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if not k.endswith('_serial')},indent=2))


if __name__=='__main__':main()
