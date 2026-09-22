from pathlib import Path
import difflib,json
R=Path(__file__).resolve().parents[1]
p=R/'engines/obsidian/src/render.cpp';b=R/'provenance/native-before/engines/obsidian/src/render.cpp';b.parent.mkdir(parents=True,exist_ok=True)
if b.exists():s=b.read_text()
else:s=p.read_text();b.write_text(s)
old=s
s=s.replace('#include "scene_maps.hpp"','#include "environment_sampler.hpp"\n#include "scene_maps.hpp"')
s=s.replace('result+=throughput*sky(ray.d);break;', 'double mis=first?1.:power_heuristic(lastpdf,environment_pdf(ray.d));result+=throughput*sky(ray.d)*mis;break;')
anchor='Vec3 wi=sample_bsdf(m,n,wo,r);'
s=s.replace(anchor,'''// R2: explicit HDR-environment next-event sampling; the escape path uses
  // the matching PDF above. No screen-space ambient term replaces transport.
  double epdf=0;Vec3 ed=sample_environment(r,epdf);auto ee=bsdf(m,albedo,n,wo,ed);
  if(epdf>0&&dot(h.gn,ed)>0&&dot(n,ed)>0&&ee.pdf>0&&!bvh.occluded({offset(h.p,h.gn,ed),ed},1e8))
      result+=throughput*ee.f*sky(ed)*(dot(n,ed)*power_heuristic(epdf,ee.pdf)/epdf);
  '''+anchor)
s=s.replace('prepare_lights();prepare_sky();','prepare_lights();prepare_sky();prepare_environment_sampler();')
s=s.replace('omp_set_num_threads(4);','const char* threads=std::getenv("OMP_NUM_THREADS");omp_set_num_threads(threads?std::max(1,std::atoi(threads)):4);')
s=s.replace('#include <omp.h>','#include <omp.h>\n#include <cstdlib>')
s=s.replace('CYBR LIGHT core / scene-specific CPU bridge','CYBR SCENES R2 / CYBR LIGHT CPU bridge, explicit HDR MIS')
assert s!=old
p.write_text(s)
q=R/'engines/obsidian/src/scene_maps.hpp';qb=R/'provenance/native-before/engines/obsidian/src/scene_maps.hpp';qb.parent.mkdir(parents=True,exist_ok=True)
if qb.exists():t=qb.read_text()
else:t=q.read_text();qb.write_text(t)
# Lower artistic emission amplification; Planck spectra and radiance mip averages
# remain unchanged. This is explicitly an authored exposure/appearance choice.
u=t.replace('constexpr double emission_gain=28.0;','constexpr double emission_gain=19.0;')
q.write_text(u)
with (R/'provenance/renderer-upgrade.diff').open('a') as f:
 for file,a,bv in [(p,old,s),(q,t,u)]:f.writelines(difflib.unified_diff(a.splitlines(True),bv.splitlines(True),fromfile='a/'+str(file.relative_to(R)),tofile='b/'+str(file.relative_to(R))))
print('Obsidian: explicit environment sampling with MIS; isolated emission gain change recorded.')
