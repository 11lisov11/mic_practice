"""Offline experimental RK4-consistent EKF covariance; never installs images."""
import json
import os
import shutil
from pathlib import Path
from investigate_remaining_observer_nis import ROOT, RELEASE as BASE, digest

OUT=ROOT/'artifacts/live_bench_20261117/observer_variational_r1'
NEW=(2026111711,2026111712)


def read(path):return path.read_text(encoding='utf8')
def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(value,encoding='utf8')


def main():
    assert not OUT.exists(), 'Do not overwrite experimental sources/results'
    protected=json.loads(read(BASE/'source_hashes.json'))
    for relative,expected in protected.items():assert digest(BASE/relative)==expected,relative
    for folder in ('nucleo','UNOQ_MOTOR','libraries','web_hmi'):
        def cp(src,dst):
            parts=Path(src).relative_to(BASE/folder).parts
            if folder=='libraries' or (folder=='nucleo' and parts[0] in ('Drivers','MCSDK_v6.4.2-Full')):
                os.link(src,dst);return dst
            return shutil.copy2(src,dst)
        shutil.copytree(BASE/folder,OUT/folder,copy_function=cp,
                        ignore=shutil.ignore_patterns('Debug','Release','__pycache__','*.pyc','*.log'))
    for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi'):
        for path in (OUT/folder).rglob('*'):
            if path.is_file():
                old=read(path);new=old.replace('2026111611',str(NEW[0])).replace('2026111612',str(NEW[1]))
                if new!=old:write(path,new)
    header=OUT/'nucleo/Inc/motor_control.h';s=read(header)
    begin=s.index('  ma_derivative(m,o->x,va,vb,k[0],a);')
    end=s.index('  for(unsigned i=0;i<6;i++)for(unsigned j=0;j<6;j++){\n    float v=0;',begin)
    replacement='''  /* Experimental RK4 variational transition: differentiate the SAME four
   * nonlinear integration stages as the state. Q/R and validity gates are
   * unchanged. Existing three matrix workspaces are reused; only one row
   * (24 bytes) is added to foreground stack. No fast IRQ work is added. */
  const float stage_h[4]={0,dt*.5f,dt*.5f,dt};
  const float weight[4]={1.f,2.f,2.f,1.f};
  for(unsigned stage=0;stage<4;++stage){
    if(!stage)memcpy(z,o->x,sizeof(z));
    else for(unsigned i=0;i<6;++i)z[i]=o->x[i]+stage_h[stage]*k[stage-1U][i];
    ma_derivative(m,z,va,vb,k[stage],a);
    if(stage){
      for(unsigned i=0;i<6;++i){
        float row[6];
        for(unsigned j=0;j<6;++j){
          float v=0;
          for(unsigned n=0;n<6;++n)v+=a[i][n]*tmp[n][j];
          row[j]=a[i][j]+stage_h[stage]*v;
        }
        memcpy(a[i],row,sizeof(row));
      }
    }
    for(unsigned i=0;i<6;++i)for(unsigned j=0;j<6;++j)
      f[i][j]=(stage?f[i][j]:(i==j?1.f:0.f))+dt*weight[stage]*a[i][j]/6.f;
    if(stage<3U)memcpy(tmp,a,sizeof(a));
  }
  for(unsigned i=0;i<6;i++)o->x[i]+=dt*(k[0][i]+2*k[1][i]+2*k[2][i]+k[3][i])/6;
'''
    s=s[:begin]+replacement+s[end:]
    s=s.replace('RK4 state integration and second-order covariance transition;',
                'RK4 state integration and RK4 variational covariance transition;')
    write(header,s)
    unchanged=['nucleo/Inc/foc_experiment.h','nucleo/Src/current_shunt.c',
               'nucleo/Inc/current_adc_window_plan.h','nucleo/Inc/current_adc_deadline.h',
               'nucleo/Inc/observer_applied_voltage.h','nucleo/Inc/observer_current_window.h',
               'nucleo/Inc/local_stop.h','nucleo/Inc/first_break_snapshot.h']
    for relative in unchanged:
        expected=read(BASE/relative).replace('2026111611',str(NEW[0])).replace('2026111612',str(NEW[1]))
        assert read(OUT/relative)==expected,relative
    files={str(path.relative_to(OUT)):digest(path) for folder in ('nucleo/Inc','nucleo/Src','UNOQ_MOTOR','web_hmi')
           for path in (OUT/folder).rglob('*') if path.is_file()}
    write(OUT/'source_hashes.json',json.dumps(files,indent=2)+'\n')
    write(OUT/'manifest.json',json.dumps(dict(pair=NEW,base_pair=[2026111611,2026111612],
        installed=False,hardware_commands=0,experimental=True,approved_for_powered_test=False,
        hardware_NIS_root_cause_proven=False,target_timing_qualified=False,
        Q_R_gates_protections_and_profile_limits_unchanged=True,
        unchanged_modules=unchanged),indent=2)+'\n')
    print('Prepared experimental sources only',OUT)


if __name__=='__main__':main()
