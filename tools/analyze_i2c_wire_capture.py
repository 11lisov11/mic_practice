"""Decode a CRC-verified saved HMI status and export nominal-time I2C VCD."""
import argparse,json
from pathlib import Path
from ipm_break_wifi_selftest import load_module
import prepare_i2c_wire_capture as p

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--status',type=Path,required=True)
    parser.add_argument('--outdir',type=Path,required=True);args=parser.parse_args()
    assert not args.outdir.exists(),'Preserve existing evidence; choose a new output directory'
    saved=json.loads(args.status.read_text(encoding='utf-8-sig'));saved=saved.get('last',saved)
    h=load_module(p.OUT/'web_hmi/server.py');decoded=h.with_i2c_first_fault(saved)
    if decoded.get('enc_wire_decode_valid')!=1 or not decoded.get('enc_wire_record'):
        raise ValueError(decoded.get('enc_wire_error','No complete waveform in saved status'))
    record=decoded['enc_wire_record'];raw=bytes.fromhex(saved['enc_wire_hex'])
    args.outdir.mkdir(parents=True)
    p.write(args.outdir/'decoded.json',json.dumps(record,indent=2)+'\n')
    (args.outdir/'wire.bin').write_bytes(raw)
    lines=['$timescale 1 ps $end','$scope module i2c $end',
      '$var wire 1 ! SCL $end','$var wire 1 " SDA $end','$upscope $end',
      '$enddefinitions $end','$comment Nominal timer timestamps; DMA latency/jitter not measured. $end']
    prev=None
    for i in range(record['samples']):
        value=(raw[48+i//4]>>(2*(i%4)))&3
        if value==prev:continue
        lines+=['#'+str(i*20*10**12//170000000),str(value&1)+'!',str((value>>1)&1)+'"'];prev=value
    p.write(args.outdir/'wire.vcd','\n'.join(lines)+'\n')
    p.write(args.outdir/'provenance.json',json.dumps(dict(input=str(args.status.resolve()),input_sha256=p.sha(args.status),
      decoder_sha256=p.sha(p.OUT/'web_hmi/server.py'),hardware_commands=0,nominal_timing_only=True),indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='transitions'}))
if __name__=='__main__':main()
