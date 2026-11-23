"""Actual asynchronous OFF-only IRQ profiler; no real peripheral writes."""
import prepare_standstill_irq_timing as package
source=package.read(package.ROOT/'tools/test_standstill_timing.py').replace('import prepare_standstill_timing as p',
 'import prepare_standstill_irq_timing as p\np.BASE=p.ROOT/"artifacts/live_bench_20261029/standstill_commissioning_r1"')
source=source.replace('2026102933','2026102937').replace('2026102934','2026102938')
source=source.replace("profile=function(source,'mi_native_profile_off')","profile=function(source,'ma_native_profile_tick')")
source=source.replace('sample.zero=1;mi_native_profile_off();',
 'sample.zero=1;for(unsigned i=0;i<1100&&!id_profile_cycles;i++){mi_native_profile_off();ma_native_profile_tick();}')
if __name__=='__main__':exec(compile(source,__file__,'exec'),globals())
