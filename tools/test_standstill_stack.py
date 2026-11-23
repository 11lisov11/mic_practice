"""Reuse native timing/guard checks against the final pair, plus stack bounds."""
import prepare_standstill_stack as package
from pathlib import Path
source=package.read(package.ROOT/'tools/test_standstill_timing.py').replace('import prepare_standstill_timing as p',
 'import prepare_standstill_stack as p\np.BASE=p.ROOT/"artifacts/live_bench_20261029/standstill_commissioning_r1"')
source=source.replace('2026102933','2026102935').replace('2026102934','2026102936')
if __name__=='__main__':exec(compile(source,str(Path(__file__)), 'exec'),globals())
