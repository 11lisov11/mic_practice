"""Instrument the first rejected passive page; preserve all rejection decisions."""
import argparse,ast,json,shutil
from pathlib import Path
from prepare_pwm_filter_pair import sha,write,change
from prepare_ipm_break_wifi import source_hashes
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'artifacts/live_bench_20261014/pwm_filter_pair_r4'

REJECT_TYPES='''enum bw_reject_reason {
  BW_REJECT_NONE=0, BW_REJECT_FRAME_CRC=1, BW_REJECT_HEADER=2,
  BW_REJECT_PAGE_LAYOUT=3, BW_REJECT_PEER_BUILD=4, BW_REJECT_NOT_FRESH_OFF=5,
  BW_REJECT_RESERVED=6, BW_REJECT_PADDING=7, BW_REJECT_DUPLICATE=8,
  BW_REJECT_RECORD_CRC=9, BW_REJECT_RECORD_ABI=10, BW_REJECT_WINDOW_KIND=11
};
typedef struct {
  bool valid;
  uint8_t reason;
  uint32_t now_ms, peer_build, good_pages_before;
  bool fresh_off;
  uint8_t bp_status, pwm_enabled;
  uint32_t rsp_age_ms;
  uint8_t packet[UV3_FRAME];
} bw_first_reject;

'''

REJECT_HELPER='''/* Bounded observation only: neither ACK nor control/watchdog state changes. */
static inline bool bw_note_reject(bw_receiver *rx, unsigned reason,
    const uint8_t *packet, uint32_t peer_build, bool fresh_off, uint32_t now_ms) {
  bw_increment(&rx->bad_pages);
  if (!rx->first_reject.valid) {
    rx->first_reject.reason=(uint8_t)reason;
    rx->first_reject.now_ms=now_ms;
    rx->first_reject.peer_build=peer_build;
    rx->first_reject.good_pages_before=rx->good_pages;
    rx->first_reject.fresh_off=fresh_off;
    memcpy(rx->first_reject.packet,packet,UV3_FRAME);
    rx->first_reject.valid=true;
  }
  return false;
}
'''

RECEIVE='''static inline bool bw_receive(bw_receiver *rx, const uint8_t *packet,
                              uint32_t peer_build, bool peer_fresh_off, uint32_t now_ms) {
  unsigned kind=packet[3], page=packet[4];
  unsigned reason=BW_REJECT_NONE;
  if (packet[0]!=0x55 || packet[1]!=0xaa || packet[2]!=BW_VERSION) reason=BW_REJECT_HEADER;
  else if (!uv3_crc_ok(packet)) reason=BW_REJECT_FRAME_CRC;
  else if (kind>1 || page>=BW_PAGES || packet[5]!=BW_PAGES) reason=BW_REJECT_PAGE_LAYOUT;
  else if (peer_build!=BW_NUCLEO_BUILD || bw_u32(packet+6)!=peer_build) reason=BW_REJECT_PEER_BUILD;
  else if (!peer_fresh_off) reason=BW_REJECT_NOT_FRESH_OFF;
  else if (packet[38]!=0) reason=BW_REJECT_RESERVED;
  if (reason!=BW_REJECT_NONE) return bw_note_reject(rx,reason,packet,peer_build,peer_fresh_off,now_ms);
  unsigned offset=page*BW_CHUNK, length=BW_BYTES-offset;
  if (length>BW_CHUNK) length=BW_CHUNK;
  for (unsigned i=length;i<BW_CHUNK;++i) if (packet[14+i]!=0) {
    return bw_note_reject(rx,BW_REJECT_PADDING,packet,peer_build,peer_fresh_off,now_ms);
  }
  bw_stage *stage=&rx->stage[kind];
  uint32_t crc=bw_u32(packet+10);
  if (!stage->mask || stage->crc!=crc || (uint32_t)(now_ms-stage->started_ms)>BW_TIMEOUT_MS) {
    memset(stage,0,sizeof(*stage)); stage->crc=crc; stage->started_ms=now_ms;
  }
  if ((stage->mask&(1U<<page)) && memcmp(stage->data+offset,packet+14,length)!=0) {
    stage->mask=0;
    return bw_note_reject(rx,BW_REJECT_DUPLICATE,packet,peer_build,peer_fresh_off,now_ms);
  }
  memcpy(stage->data+offset,packet+14,length);
  stage->mask|=(uint8_t)(1U<<page);
  bw_increment(&rx->good_pages);
  if (stage->mask==((1U<<BW_PAGES)-1U)) {
    reason=BW_REJECT_NONE;
    if (uv3_crc32c(stage->data,BW_BYTES)!=crc) reason=BW_REJECT_RECORD_CRC;
    else if (!bw_record_valid(stage->data)) reason=BW_REJECT_RECORD_ABI;
    else if (kind==1 && bw_u32(stage->data)!=0 && bw_u32(stage->data+88)!=1) reason=BW_REJECT_WINDOW_KIND;
    if (reason!=BW_REJECT_NONE) {
      stage->mask=0; return bw_note_reject(rx,reason,packet,peer_build,peer_fresh_off,now_ms);
    }
    memcpy(rx->data[kind],stage->data,BW_BYTES);
    rx->complete[kind]=true; rx->received_ms[kind]=now_ms; stage->mask=0;
  }
  return true;
}
'''

FORMAT='''  const auto &rejected=g_break_wire.first_reject;
  s += " mc_break_reject_valid="; s += String((unsigned)rejected.valid);
  s += " mc_break_reject_code="; s += String((unsigned)rejected.reason);
  s += " mc_break_reject_ms="; s += String((unsigned long)rejected.now_ms);
  s += " mc_break_reject_peer_fw="; s += String((unsigned long)rejected.peer_build);
  s += " mc_break_reject_fresh_off="; s += String((unsigned)rejected.fresh_off);
  s += " mc_break_reject_bp_status="; s += String((unsigned)rejected.bp_status);
  s += " mc_break_reject_pwm="; s += String((unsigned)rejected.pwm_enabled);
  s += " mc_break_reject_rsp_age_ms="; s += String((unsigned long)rejected.rsp_age_ms);
  s += " mc_break_reject_good_before="; s += String((unsigned long)rejected.good_pages_before);
  s += " mc_break_reject_packet_hex=";
  if (!rejected.valid) s += "-";
  else for (unsigned i=0;i<UV3_FRAME;++i) {
    s += break_hex[rejected.packet[i]>>4]; s += break_hex[rejected.packet[i]&15];
  }
'''

HMI_HELPER='''def break_reject_status(kv):
    names=("valid", "code", "ms", "peer_fw", "fresh_off", "bp_status", "pwm", "rsp_age_ms", "good_before")
    result={}
    try:
        for name in names:
            value=int(kv.get("mc_break_reject_"+name, "0"))
            if not 0<=value<=0xffffffff: raise ValueError("reject field outside uint32")
            result["mc_break_reject_"+name]=value
        packet=kv.get("mc_break_reject_packet_hex", "-")
        result["mc_break_reject_packet_hex"]=packet
        reasons={1:"FRAME_CRC",2:"HEADER",3:"PAGE_LAYOUT",4:"PEER_BUILD",5:"NOT_FRESH_OFF",
                 6:"RESERVED",7:"PADDING",8:"DUPLICATE",9:"RECORD_CRC",10:"RECORD_ABI",11:"WINDOW_KIND"}
        code=result["mc_break_reject_code"]
        record_ok=(result["mc_break_reject_valid"]==1 and code in reasons and
            result["mc_break_reject_fresh_off"] in (0,1) and result["mc_break_reject_pwm"] in (0,1) and
            len(packet)==86 and all(c in "0123456789abcdefABCDEF" for c in packet))
        result["mc_break_reject_record_valid"]=int(record_ok)
        result["mc_break_reject_reason"]=reasons[code] if record_ok else "UNAVAILABLE"
        return result
    except (ValueError,TypeError):
        return {"mc_break_reject_record_valid":0,"mc_break_reject_reason":"INVALID_METADATA"}

'''

def prepare(out):
    assert json.loads((BASE/'qualification/report.json').read_text())['pass']
    out.mkdir(parents=True,exist_ok=False)
    pairs={'production':((2026101407,2026101406),(2026101409,2026101408)),
           'fixture':((2026101496,2026101497),(2026101494,2026101495))}
    for name,(old,new) in pairs.items():
        original=json.loads((BASE/name/'manifest.json').read_text())
        assert source_hashes(BASE/name/'nucleo')==original['nucleo_source_sha256']
        assert source_hashes(BASE/name/'UNOQ_MOTOR')==original['uno_source_sha256']
        p=out/name
        for tree in ('nucleo','UNOQ_MOTOR','web_hmi'):
            shutil.copytree(BASE/name/tree,p/tree,ignore=shutil.ignore_patterns('Debug','Release','.metadata','__pycache__'))
        change(p/'nucleo/Src/main.c',f'MIC_NUCLEO_FW_BUILD_ID {old[1]}UL',f'MIC_NUCLEO_FW_BUILD_ID {new[1]}UL')
        change(p/'UNOQ_MOTOR/UNOQ_MOTOR.ino',f'FW_BUILD_ID = {old[0]}U',f'FW_BUILD_ID = {new[0]}U')
        for tree in ('nucleo/Inc','UNOQ_MOTOR'):
            h=p/tree/'break_wire.h';text=h.read_text()
            text=text.replace(f'BW_NUCLEO_BUILD {old[1]}UL',f'BW_NUCLEO_BUILD {new[1]}UL')
            text=text.replace('typedef struct {\n  bw_stage stage[2];',REJECT_TYPES+'typedef struct {\n  bw_stage stage[2];')
            text=text.replace('  uint32_t bad_pages;','  uint32_t bad_pages;\n  bw_first_reject first_reject;')
            text=text.replace('static inline void bw_reset(',REJECT_HELPER+'\nstatic inline void bw_reset(')
            start=text.index('static inline bool bw_receive(');end=text.rindex('#endif')
            text=text[:start]+RECEIVE+text[end:];write(h,text)
        peer=p/'UNOQ_MOTOR/nucleo_fault_diagnostics.h'
        peers=f'build == {old[1]}U || build == {new[1]}U'
        if name=='fixture':peers+=' || build == 2026101408U'
        change(peer,f'build == {old[1]}U;',peers+';')
        ino=p/'UNOQ_MOTOR/UNOQ_MOTOR.ino'
        change(ino,'  static const char break_hex[] = "0123456789abcdef";',
               '  static const char break_hex[] = "0123456789abcdef";\n'+FORMAT)
        change(ino,'      if (buf[2] == BW_VERSION) {','''      if (buf[2] == BW_VERSION) {
        const bool had_rejection=g_break_wire.first_reject.valid;
        const uint32_t observed_ms=millis();
        const uint32_t observed_age=(uint32_t)(observed_ms-g_bp_last_rsp_ms);
        const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&
            (g_bp_status & 0x22U) == 0U && observed_age < 300U;''')
        change(ino,'          bw_increment(&g_break_wire.bad_pages);',
            '          (void)bw_note_reject(&g_break_wire,BW_REJECT_FRAME_CRC,buf,g_bp_fw_build,fresh_off,observed_ms);')
        change(ino,'''          const bool fresh_off = g_bp_mcsdk_telemetry && !g_pwm_enabled &&
              (g_bp_status & 0x22U) == 0U && (uint32_t)(millis()-g_bp_last_rsp_ms) < 300U;
          (void)bw_receive(&g_break_wire,buf,g_bp_fw_build,fresh_off,millis());''',
            '          (void)bw_receive(&g_break_wire,buf,g_bp_fw_build,fresh_off,observed_ms);')
        change(ino,'''        continue;
      }
      const bool integrity_ok''','''        if (!had_rejection && g_break_wire.first_reject.valid) {
          g_break_wire.first_reject.bp_status=g_bp_status;
          g_break_wire.first_reject.pwm_enabled=g_pwm_enabled;
          g_break_wire.first_reject.rsp_age_ms=observed_age;
        }
        continue;
      }
      const bool integrity_ok''')
        web=p/'web_hmi/server.py';text=web.read_text()
        text=text.replace('(2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497)',
          '(2026101102, 2026101204, 2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495)')
        text=text.replace('in (2026101404, 2026101499, 2026101406, 2026101497):',
          'in (2026101404, 2026101499, 2026101406, 2026101497, 2026101408, 2026101495):')
        if name=='fixture':text=text.replace('(2026101496, 2026101497)','(2026101494, 2026101495)')
        text=text.replace('def break_wire_status(',HMI_HELPER+'def break_wire_status(')
        text=text.replace('                **break_wire_status(kv),','                **break_wire_status(kv),\n                **break_reject_status(kv),')
        text=text.replace('        "mc_break_rx_good",\n        "mc_break_rx_bad",','''        "mc_break_rx_good",
        "mc_break_rx_bad",
        "mc_break_reject_record_valid", "mc_break_reject_reason", "mc_break_reject_code",
        "mc_break_reject_ms", "mc_break_reject_peer_fw", "mc_break_reject_fresh_off",
        "mc_break_reject_bp_status", "mc_break_reject_pwm", "mc_break_reject_rsp_age_ms",
        "mc_break_reject_good_before", "mc_break_reject_packet_hex",''')
        ast.parse(text);write(web,text)
        manifest=dict(original,pair=list(new),nucleo_source_sha256=source_hashes(p/'nucleo'),
          uno_source_sha256=source_hashes(p/'UNOQ_MOTOR'),hmi_sha256=sha(web),reject_instrumentation=True,
          reject_acceptance_policy_changed=False)
        write(p/'manifest.json',json.dumps(manifest,indent=2)+'\n')
        assert (p/'nucleo/Inc/break_wire.h').read_bytes()==(p/'UNOQ_MOTOR/break_wire.h').read_bytes()
    shutil.copytree(BASE/'fastmath',out/'fastmath')
    write(out/'manifest.json',json.dumps(dict(production_pair=[2026101409,2026101408],fixture_pair=[2026101494,2026101495],
       predecessor_pair=[2026101407,2026101406],predecessor_hmi_sha256=sha(BASE/'production/web_hmi/server.py'),
       hardware_commands=0,hv_release_approved=False),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--outdir',type=Path,required=True);a=p.parse_args();prepare(a.outdir.resolve())
