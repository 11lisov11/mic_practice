"""Export a scientific field image directly from the native FEMM solution."""
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.tri as tri

ROOT=Path(__file__).resolve().parent


def read_ans(path):
    lines=path.read_text().splitlines()
    pos=lines.index('[Solution]')+1
    nn=int(lines[pos]);pos+=1
    nodes=np.array([[float(x) for x in line.split()[:4]] for line in lines[pos:pos+nn]])
    pos+=nn
    ne=int(lines[pos]);pos+=1
    elements=np.array([[int(x) for x in line.split()[:3]] for line in lines[pos:pos+ne]])
    return nodes,elements


def main():
    nodes,elements=read_ans(ROOT/'femm'/'hub_nonlinear.ans')
    xy=nodes[:,:2]
    a=nodes[:,2]+1j*nodes[:,3]
    x=xy[elements,0]; y=xy[elements,1]; av=a[elements]
    det=(x[:,1]-x[:,0])*(y[:,2]-y[:,0])-(x[:,2]-x[:,0])*(y[:,1]-y[:,0])
    dadx=np.sum(av*np.stack([y[:,1]-y[:,2],y[:,2]-y[:,0],y[:,0]-y[:,1]],axis=1),axis=1)/det
    dady=np.sum(av*np.stack([x[:,2]-x[:,1],x[:,0]-x[:,2],x[:,1]-x[:,0]],axis=1),axis=1)/det
    # t=0 field, not a made-up colour scale or a phasor with doubled amplitude.
    b=np.sqrt(dadx.real**2+dady.real**2)*1000
    triang=tri.Triangulation(xy[:,0],xy[:,1],elements)
    fig,ax=plt.subplots(figsize=(8.5,7.5),layout='constrained')
    plot=ax.tripcolor(triang,b,shading='flat',cmap='turbo',vmin=0,vmax=2,rasterized=True)
    amax=np.max(abs(a.real))
    ax.tricontour(triang,a.real,levels=np.linspace(-amax,amax,26),colors='black',linewidths=.3,alpha=.6)
    ax.set(aspect='equal',xlim=(-112,112),ylim=(-112,112),xlabel='x, mm',ylabel='y, mm',
           title='Hub ACIM: nonlinear FEMM check, M-19 reference B-H\n35 A phase peak, 3 Hz slip; instantaneous field t=0')
    fig.colorbar(plot,ax=ax,label='Instantaneous |B|, T')
    fig.savefig(ROOT/'results'/'magnetic_field.png',dpi=170)
    plt.close(fig)
    files=list(ROOT.glob('*.py'))+list(ROOT.glob('*.json'))+list((ROOT/'femm').glob('*.fem'))+list((ROOT/'femm').glob('*.ans'))+list((ROOT/'femm').glob('*.json'))
    files += [p for p in (ROOT/'results').glob('*') if p.name!='simulation_manifest.json' and p.is_file()]
    manifest={str(p.relative_to(ROOT)).replace('\\','/'):{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files}
    (ROOT/'results'/'simulation_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print(json.dumps({'nodes':len(nodes),'elements':len(elements),'image':'results/magnetic_field.png'}))


if __name__=='__main__':
    main()
