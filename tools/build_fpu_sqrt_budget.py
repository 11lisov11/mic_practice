"""Reproducible native build with explicit checked GNU ld square-root wrap."""
import inspect
import build_standstill_timing as base
import prepare_fpu_sqrt_budget as p


def main():
 source=inspect.getsource(base.main)
 anchor='   p.write(target,text)'
 assert source.count(anchor)==1
 source=source.replace(anchor,'''   if f.name=='makefile':
    assert text.count('-Wl,-Map=')==1
    text=text.replace('-Wl,-Map=','-Wl,--wrap=__ieee754_sqrtf -Wl,-Map=')
   p.write(target,text)''')
 scope=dict(base.__dict__,p=p);exec(compile(source,__file__,'exec'),scope);scope['main']()


if __name__=='__main__':main()
