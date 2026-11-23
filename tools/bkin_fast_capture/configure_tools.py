"""One-time offline derivation of tests, decoder and installer from r3 tools."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
T=Path(__file__).resolve().parent
def edit(path, pairs):
    s=path.read_text(encoding='utf-8-sig')
    for a,b in pairs:
        assert a in s, (path,a)
        s=s.replace(a,b)
    path.write_text(s,encoding='utf-8',newline='\n')

edit(T/'decoder.py', [
 ('Schema 3:', 'Schema 4:'), ('2026101802','2026101804'),
 ('schema!=3','schema!=4'),('period!=1000','period!=200'),('trigger>64','trigger>2048'),
 ('trigger+100000','trigger+500000'),('limit!=100000','limit!=500000'),('remaining>1024','remaining>8192'),
 ("'from_us':total-trigger,'to_us':total+count-trigger", "'from_us':(total-trigger)/5,'to_us':(total+count-trigger)/5"),
 ('trigger+65','trigger+321'),('rise+65','rise+321'),
 ('{width} мкс','{width/5:g} мкс'),('разрешение 1 мкс','разрешение 0,2 мкс'),('Разрешение 1 мкс','Разрешение 0,2 мкс'),
 ("'schema':3", "'schema':4"), ("'sample_period_us':1,'sample_rate_hz':1000000", "'sample_period_us':0.2,'sample_rate_hz':5000000"),
 ('else width,', 'else width/5,'), ('else fall-trigger,','else (fall-trigger)/5,'),('else rise-trigger,','else (rise-trigger)/5,'),
 ('1-us DMA','200-ns DMA'), ('shorter than 1 us','shorter than 0.2 us'),
 ("'Only PA6/SD is measured;", "'Requested DMA rate requires hardware throughput validation; DMA flags cannot detect every missed timer request',\n                'Only PA6/SD is measured;")])

edit(T/'update_guard.py', [('((2026101711,2026101710),(2026101803,2026101802))',
    '((2026101803,2026101802),(2026101805,2026101804))')])
edit(ROOT/'tools/install_bkin_fast_capture_pair.py', [
 ('full-pulse recorder','5-MHz diagnostic recorder'),('bkin_full_pulse_r1','bkin_fast_capture_r1'),
 ('OLD=(2026101711,2026101710); NEW=(2026101803,2026101802)',
  'OLD=(2026101803,2026101802); NEW=(2026101805,2026101804)'),
 ('tools/bkin_full_pulse/update_guard.py','tools/bkin_fast_capture/update_guard.py'),
 ('mic_ai.bkin_full_pulse_candidate.v1','mic_ai.bkin_fast_capture_candidate.v1'),
 ('bkin_full_pulse_install_','bkin_fast_capture_install_')])

edit(T/'sim.c', [
 ('DMA_MDATAALIGN_WORD=2','DMA_MDATAALIGN_HALFWORD=1'),
 ('volatile uint32_t mic_bkin_ring[','volatile uint16_t mic_bkin_ring['),
 ('timer.ARR==169','timer.ARR==33'),
 ('(count-1)&1023','(count-1)&8191'),('1024-(count&1023)','8192-(count&8191)'),
 ('count/1000','count/5000'),('count&511','count&4095'),('count&512','count&4096'),
 ('2,0,65,100065,33','2,0,2049,502049,33'), ('0,16,1025,1','0,16,8193,1'),
 ('start+width+3000','start+width+20000'),
 ('{1,24,70,511,1024,2500,90000}','{1,2,5,120,350,511,1024,2500,93480,450000}'),
 ('{0,1,63,510,511,512,1022,1023}','{0,1,2047,4094,4095,4096,8190,8191}'),
 ('w<7','w<10'),('2048+phases[p]','16384+phases[p]'),
 ('i<105000','i<530000'),('i<2050','i<16386'),('i==2052','i==16388'),
 ('i<2000','i<10000'),('i<3000','i<30000'),
 ('i<=3072','i<=24576'),('i<2048','i<16384'),
 ('mic_bkin_completed=0xfffffe00U','mic_bkin_completed=0xfffff000U'),
 ('i=0xfffffe01U;i!=1500U','i=0xfffff001U;i!=10000U')])

edit(ROOT/'tools/bkin_fast_capture_selftest.py', [
 ('bkin_full_pulse_r1','bkin_fast_capture_r1'),
 ('artifacts/live_bench_20261017/bkin_dma_arr_fix_r1','artifacts/live_bench_20261018/bkin_full_pulse_r1'),
 ('tools/bkin_full_pulse','tools/bkin_fast_capture'), ('bkin_full_pulse_hmi','bkin_fast_capture_hmi'),
 ('2026101802','2026101804'),('2026101803','2026101805'),
 ("d['pulse_width_us']==width", "d['pulse_width_us']==width/5"),
 ('pulse_70_511.bin','pulse_350_4095.bin'),
 ('(24,65),(28,100065)','(24,2049),(28,502049)'),('(56,1025)','(56,8193)'),
 (".replace('2026101710','2026101804').replace('#include \"bkin_wave_capture.h\"','#include \"bkin_wave_capture.h\"\\n#include \"pulse_core.h\"')",
  ".replace('2026101802','2026101804').replace('volatile uint32_t mic_bkin_ring[','volatile uint16_t mic_bkin_ring[')"),
 ("'nucleo/Inc/bkin_wave_capture.h')", "'nucleo/Inc/bkin_wave_capture.h','nucleo/Inc/pulse_core.h','nucleo/Inc/pulse_record.h')"),
 ('import install_bkin_full_pulse_pair as installer','import install_bkin_fast_capture_pair as installer'),
 ("'fw_build':2026101711,'mc_fw_build':2026101710", "'fw_build':2026101803,'mc_fw_build':2026101802")])
print('offline tools configured')
