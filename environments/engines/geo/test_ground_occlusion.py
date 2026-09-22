"""Self-contained certificate/interval regression, without the large forest mesh."""
from pathlib import Path
import json,subprocess,struct
import numpy as np

def run(root:Path):
    native=root/'cybr-geo/native';out=root/'verification';out.mkdir(exist_ok=True)
    binary=out/'test_ground_occlusion_r4'
    cmd=['g++','-std=c++17','-O3','-march=native','-fno-math-errno','-fno-trapping-math','-fopenmp',str(native/'test_ground_occlusion_r4.cpp'),'-o',str(binary)]
    subprocess.run(cmd,check=True)
    nx,ny=401,601;x=np.linspace(-20,20,nx);y=np.linspace(-10,50,ny);xx,yy=np.meshgrid(x,y)
    center=.8*np.sin(yy*.17)
    # Exact linear-triangle cell minima bound this separately defined fixture.
    z=.6-.85*np.exp(-((xx-center)/1.4)**4)+.035*np.sin(xx*1.9)*np.sin(yy*.42)
    minima=np.minimum(np.minimum(z[:-1,:-1],z[1:,:-1]),np.minimum(z[:-1,1:],z[1:,1:])).astype('<f4')
    path=out/'synthetic_ground_certificate.bin'
    with path.open('wb') as f:
        f.write(struct.pack('<4sII6f',b'GOC1',nx,ny,float(x[0]),float(x[-1]),float(y[0]),float(y[-1]),float(z.min()),float(z.max())));f.write(minima.tobytes())
    report=json.loads(subprocess.check_output([str(binary),str(path)],text=True))
    bad=out/'truncated_ground_certificate.bin';bad.write_bytes(path.read_bytes()[:100])
    reject=subprocess.run([str(binary),str(bad)],capture_output=True,text=True)
    report['truncated_certificate_rejected']=reject.returncode!=0
    report['compile_command']=cmd;report['fixture_not_full_scene']=True
    report['passed']=report['passed'] and report['truncated_certificate_rejected']
    return report

if __name__=='__main__':
    print(json.dumps(run(Path(__file__).resolve().parent),indent=2))
